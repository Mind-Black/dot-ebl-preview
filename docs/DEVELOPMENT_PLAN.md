# Combined development plan

Status: revised after the independent [Critic review](CRITIC_REVIEW.md); amendment responses are in [REVIEW_RESPONSE.md](REVIEW_RESPONSE.md). Scope is planning; no application implementation is claimed. Source evidence and feature IDs are in [SOURCE_AUDIT.md](SOURCE_AUDIT.md), and translation details in [RAITH_PORT.md](RAITH_PORT.md).

Build a local Python application in `dot-ebl-preview` with one authoritative physical design shared by RGB import, optical preview, diagnostics, and Raith layout export. Keep pygame/OpenGL initially to reuse the existing renderer and avoid adding a web or desktop framework. Provide a headless Python API and CLI so fabrication does not depend on opening a graphics window.

## 1. Decisions and defaults

1. Canonical design data contains physical parameters, activity, geometry configuration, and provenance. RGB images are a numeric interchange format; displayed optical RGB is a separate output.
2. New inputs never pass through HSL/HSV. Legacy images require an explicitly selected importer and source preset. Never auto-detect a parameter image by its colors or filename.
3. Use integer nanometres for pitch, period, and quantized geometry; float64 degrees for processed angles. Preserve source codes/metadata alongside decoded values. GPU buffers use derived float32 values in explicitly declared units.
4. Default fabrication recipe: 20 µm pitch, Raith single-pixel lines (`path` with width 0), 0.9–1.2 µm period range with 0.01 µm steps, angles −90..90°, layer 1, dose factor 1, no smoothing or radial override unless selected. Provide a `learning-shaders` recipe with 60 µm pitch, ±45° initial angle range, its radial parameters and Gaussian smoothing. Both recipes use corrected masks and shared coordinates. The user's follow-up explicitly replaces filled polygons and the old 0.1 µm linewidth; that linewidth is retained only as legacy provenance, never silently used to widen paths.
5. Preserve full arrays, sample assets, plots, filters, radial operations, calibration data, mesh/material utilities, animation, parameter text exports, layout hierarchy and progress. Dormant Unity algorithms are explicit presets; restoring a Unity runtime is outside the existing Python application's behavior.
6. Translate the necessary Raith algorithms into a self-contained Python subpackage. gdsfactory is allowed only in a temporary baseline-generation environment; it is absent from the delivered application's dependencies.

## 2. RGB encoding contract

Use versioned metadata (`encoding.json`) with a required encoding ID, bit depth, channel semantics, physical ranges/lookup tables, mask codes, row order, and source hash. Reject absent/unknown metadata unless the user explicitly supplies a profile. Do not infer ranges from image extrema.

Recommended initial profiles:

| Profile | R | G | B | Purpose |
|---|---|---|---|---|
| `rgb8-indexed-v1` | Index into an explicit period table | Index into an explicit angle table | 0 inactive, 255 active | Easy lossless coding of existing discrete design palettes |
| `rgb16-fixed-v1` | Period in integer nm | Angle in 0.01° units, offset by 32768 | 0 inactive, 65535 active | Direct finer-resolution physical interchange |

Default RGB8 tables are `period_nm = 900 + 10*R` for R=0..30 and `angle_deg = G-90` for G=0..180; other active-pixel R/G codes are invalid. Alternative metadata tables allow the eight calibrated periods, ±45° ranges, exact zero, and other finite palettes without changing code. LUT entries must be unique, finite and within declared limits. Reserved B values are errors, not implicit brightness or dose. Alpha is not a second conflicting activity channel: parameter inputs must be RGB; legacy RGBA requires an explicit flatten/mask policy during migration. Black and white have no special meaning outside the legacy importer.

For RGB16, active period codes must be positive and within configured optical/fabrication limits. Signed angles decode as `(G-32768)/100`; encode with an explicit half-away-from-zero rounding rule. Validate bounds before uint16 conversion to avoid overflow. Do not use the entire representable code range as an assumed process capability.

RGB8 code values and table entries round-trip exactly. RGB16 is exact on its declared 1 nm / 0.01° grid; exporting arbitrary physical values introduces at most 0.5 nm and 0.005° quantization error before geometry construction. Report that error and require a caller-selected policy (`reject` or `quantize`) for off-grid export. Eliminating HSL conversion errors does not eliminate finite image precision, floating-point arithmetic, or the Raith 1 nm geometry grid.

All parameter-image exports default to `reject` unless exact representability is proven. RGB8 period tables use canonical integer nm and angle tables use persisted float64 degrees; exact export compares these declared decoded representations, without an arbitrary near-equality tolerance. Under explicit `quantize`, select the nearest entry by absolute distance in physical units, using directed degree distance for angles and lowest table index to break ties. Reject values outside table minima/maxima unless a separately selected `clip` policy allows it. No modulo-180 distance, automatic palette extension or silent clipping. RGB16 uses the stated half-away rule. Export reports max/RMS period and directed-angle errors, changed active-pixel counts, clipping counts, selected codes/table/policy and any directed-branch change. Encode then decode to verify the emitted image and metadata before publication. Never replace the authoritative Design as a side effect. Test RGB8 0.5° ties, sparse/custom palettes, limits, and the 16-bit fixed grid; all policies preserve activity exactly.

Processed Gaussian/bilateral/radial angles may contain many more distinct values than an RGB8 palette. Save the authoritative processed design as typed arrays plus JSON (`design.npz` with `allow_pickle=False` on read); do not silently re-encode it to RGB or quantize it differently for preview and export. Arrays include angle_deg float64, period_nm integer, activity bool, optional region IDs, and recipe metadata. Exact reproducibility is through this design artifact. RGB output is a deliberate interchange action with an error report.

Appearance data is separate: optionally retain the original appearance RGB asset and a float32 per-pixel fallback-intensity field, its sampling policy and declared color space. These travel with the project artifact and preview hash but never encode period, angle, activity or dose. The Unity-compatible dark fallback uses the declared source sample's channel mean divided by five when all computed RGB components are ≤0.01; it cannot use the numeric parameter image's channel mean. New RGB-only designs default to black/no fallback unless an appearance asset or explicit fallback value is supplied. The shader file alone does not supply Unity texture-import/color-space settings, so any assumed sampling/color space is documented and exact Unity-render parity is not claimed without the original runtime configuration.

Use a verified decoder that preserves uint8/uint16 RGB samples, expands no gamma/ICC transforms, and never silently drops 16-bit channels. If OpenCV decodes BGR, reorder channels exactly once and test with asymmetric byte fixtures. No JPEG parameter images, image-editor color correction, resampling interpolation, sRGB GPU textures, mipmaps, or blending of parameter channels. Nearest-neighbor downscale works on codes/masks or decoded fields with the same explicit index selection. Keep ordinary image/color handling separate for optional visual textures.

The legacy importer freezes each original HLS mapping as a named migration mode. It records OpenCV version, original bytes, decoded values, original recipe, and a discrepancy report. Existing conversion loss cannot be recovered. It extracts hue-162 regions into an explicit mask, allowing future radial operations without color-dependent rules. Corrected mode fixes the white-mask and sentinel-filter defects; an audit-only legacy-exact mode can reproduce them for comparisons, never as the default fabrication path.

The dormant Unity source has a separate `legacy-unity-hsv` importer; it must not reuse the OpenCV HLS importer. Port the shader's HSV conversion/epsilon and period selection into a CPU migration fixture: saturation <0.1 disables diffraction; hue >0.7 selects the first calibrated period; otherwise select the nearest of the eight laser hue entries, with the first entry winning equal-distance ties. Angle is saturation*(max_angle−min_angle)+min_angle, default −10/+10°. Preserve source appearance for fallback. This import is one-time compatibility work; new design preview/export reads the resulting physical arrays and never decodes HSL/HSV again. Activity means presence of a grating, so an inactive cell may still display its independent appearance fallback. For grating zero, skip spectral division, set diffraction to finite zero, then apply the preset's fallback; this explicitly corrects the original undefined intermediate arithmetic. Fixtures include equal physical parameters with different brightness, saturation below/at/above 0.1, hue around 0.7, nearest-hue ties, RGB intensity around 0.01, and save/reload.

## 3. Shared design and coordinates

Define a validated immutable `Design` and a derived `FabricationPlan`:

- Design: shape H×W, RGB profile/source identity, activity, period_nm, angle_deg, pitch_nm, exposure_mode=`single_pixel_line`, layer, dose, region masks, ordered operations and their parameters. Width is fixed at zero for exported paths.
- FabricationPlan: unique holopixel geometry, integer-grid local two-endpoint paths, ordered placements, names, quantization statistics, extents, hashes and export settings. Both the geometry preview and writer consume this plan.
- Image index: row increases down, column increases right. Fabrication centers: x=(col+0.5)*pitch, y=−(row+0.5)*pitch. A centered preview applies only translation (−W*pitch/2, +H*pitch/2); it never mirrors or rescales the design independently.
- Angle: positive counterclockwise rotation about the holopixel center in the fabrication XY plane; unrotated stripes run along +X, grating normal along +Y. Optical grating vectors derive from the same transform. Scene normal/camera handedness is explicit.
- Build cell edges from integer index counts, including W+1/H+1 boundaries. Check transformed full extents and integer range, not just local vertices. Odd-nm pitch may create half-grid centers: reject or explicitly snap once into the FabricationPlan and report the choice.
- Preview/export share the same content hash and frozen snapshot. Every screenshot/diagnostic/export records it. A change to pitch, filters, masks, angle or geometry invalidates the derived plan and caches.

Operation order is fixed and stored: decode → nearest downscale → map/validate → explicit radial override → optional Gaussian/bilateral filter → optional angle quantization → build geometry/placement snapshot. Activity is carried separately through every stage. Normalized valid-only Gaussian and bilateral weights prevent invalid regions influencing valid angles; if no valid neighbors remain, retain the original valid value. Preserve scalar-angle behavior as a compatibility option; axial orientation smoothing uses doubled-angle sine/cosine with a defined fallback when the resultant magnitude is near zero.

Do not normalize fabrication angles modulo 180°. The finite set of stripe centers is anchored by the original phase formula and can be asymmetric about zero when pitch/period is not integral; a 180° rotation preserves grating orientation but may change line locations. Keep the full signed rotation in the Design/SREF. Optional axial smoothing unwraps its result to the branch closest to each original angle, choosing the numerically lower directed angle on an exact tie and retaining the original angle for a near-zero resultant. If a selected branch exceeds a profile limit, reject that operation/export with the affected cells; never silently wrap to fit. Report any deliberate 180° branch change as a geometry/phase change. Treat the filter as a deliberate geometry edit, not a proof of phase equivalence. Test θ versus θ+180° and −90/+90° crossings at 20,000 nm pitch / 900 nm period: the 22 stripe centers −9,550..+9,350 nm reflect to −9,350..+9,550 nm. Preserve distinct placements; no angle-based deduplication may collapse them.

For each legacy stripe center y = −pitch/2 + period/2 + k*period within the circular radius, compute x_max = sqrt((pitch/2)^2 − y^2), then emit exactly one Raith path from (−x_max,y) to (+x_max,y), width 0. Keep separate paths: connecting stripes into a polyline would add unintended exposure segments. Preserve stripe count/phase except genuinely zero-length chords or endpoints collapsing to the same nm coordinate, which are skipped with counted diagnostics, never converted to dots. Generate stripe indices deterministically rather than relying on floating arange endpoints. At radius boundaries, clamp only tiny arithmetic roundoff before sqrt; reject invalid physical inputs.

Half-grid local stripe centers can occur even with an even pitch when the period is odd: include 20,000 nm / 903 nm fixtures (the latter is in the existing calibrated palette). Test both signs at half-nm ties under MATLAB-compatible rounding and record actual local inter-line spacing/phase deviations separately from placement snap and reference-transform errors. The optical model can continue using nominal period for its approximation, but the geometry view and export use identical snapped paths and expose their deviation statistics.

Path width zero is the Raith representation of single-pixel exposure, not a prediction of developed linewidth. Dose factor 1 is a serialization default, not a transfer of a validated area-dose recipe to a line-dose process. A process profile must record target line-exposure settings and units separately; no automatic area→line dose conversion is assumed. Native qualification includes verification of line mode and dose interpretation in NanoSuite. Physical linewidth/beam footprint, if supplied for visual overlay, does not change exported WIDTH=0 or claim a calibrated optical response.

Retain both radial formulas and their 50-pixel center offset as named presets, applied after downsampling in resulting pixel coordinates just as in the originals. Generalize to explicit center/range/region settings. Do not silently clamp their distance ratio to one: the old normalization does not necessarily describe the farthest corner. Validate final angles against the selected profile and report out-of-range results.

## 4. Modules and public workflows

```text
pyproject.toml, dependency lock, README.md
src/dot_ebl_preview/
  core/       model, encoding, grid, operations, filters, validation
  io/         images, legacy_hls, project artifacts, text exports
  optics/     tables, CPU reference, optical presets
  preview/    pygame app, GL renderer, mesh, material, shaders
  layout/     holopixel geometry, placements, fabrication plan
  raith/      elements, structures, library, records, writer, capabilities
  diagnostics/ physical maps, channel maps, geometry inspection
  jobs/       progress, cancellation, immutable job snapshots
  cli.py, api.py
tests/        unit, integration, golden, GPU, performance
examples/     original assets, RGB examples, recipes
docs/         migration, port coverage, benchmark results, provenance
```

Runtime dependencies: NumPy, a verified image decoder (OpenCV initially also supports legacy import/bilateral baselines), SciPy for Gaussian operations, pygame, PyOpenGL, Matplotlib for diagnostics; retain pyrr initially or replace only after matrix fixture parity. The Raith writer uses standard Python `struct`/binary IO and NumPy, without a second layout generator. Pin tested compatible versions during phase 0. Keep graphics imports optional for headless export.

Workflows: `inspect`, `import-legacy`, `preview`, `export`, and `benchmark` CLI commands; equivalent typed Python functions. `build_design()` returns a Design; `build_layout()` returns a FabricationPlan; `export()` returns paths and a manifest. A documented compatibility wrapper supports the original dot-matrix arguments and write/no-write behavior with Raith result types replacing gf.Component. Diagnostics are available on demand rather than a mandatory blocking plot before each export. Text outputs keep µm periods, degree angles, row order and legacy inactive sentinels, with explicit metadata; internal arrays never use sentinels for validity.

An export job validates the entire frozen plan and builds a reproducible name map. Stage the whole output bundle in a job-specific temporary directory on the destination filesystem: `angles.txt`, `gratings.txt`, `.gds` and optionally `.csf`, plus the design artifact and appearance data if used. After all files pass checks, write a completion manifest containing their hashes and atomically publish the directory under a collision-resistant timestamped name. If the platform cannot guarantee directory publication, consumers require a final completion marker and treat its absence as incomplete. Cancellation removes only the job's temporary artifacts. Test failures/cancellation between every file and before publication; no seemingly complete layout may be paired with stale/missing parameter arrays. Progress reaches 100% and remains meaningful for zero and one active pixel. All-inactive input produces a documented empty top structure and empty-pattern diagnostic, not division by zero.

## 5. Optical preview and fidelity

First port the active spectral model into a float64 CPU reference, with captured legacy cases and explicitly corrected numerical guards. Preserve all 77 wavelengths, spectral tables, nickel reflectance, primaries, and gamut behavior. Keep the GLSL and Unity normalization/order/fallback differences as named presets. A corrected common model normalizes by illuminant luminance before reflectance, uses a coherent view/source coordinate system and finite guarded gamut mapping; label this as a model correction, not byte-equivalent old output. The model remains qualitative until checked against optical measurements.

Use OpenGL 3.3 core triangles with compact per-cell instances. The correctness path retains per-corner spectral evaluation and interpolation to match the original spatial sampling. An optional fast mode evaluates at cell centers or visible samples only; it must pass a CPU/image error comparison and display its approximation status. Do not claim one spectral result per period/angle is exact for a spatially varying point light/camera.

Provide two coordinated views: optical appearance and actual fabrication geometry. The latter draws the Raith-plan chord centerlines with a screen-space visible stroke, plus cell outlines, mask and orientation; the screen stroke never changes path WIDTH=0. Zero-width paths may be invisible in generic area-based GDS viewers, so correctness uses raw path/endpoints/width records and NanoSuite line-mode inspection rather than filled-area comparisons. Preserve square-cell optical interpolation as a compatibility mode and provide an aperture/envelope overlay matching the actual design. Viewer centering, normal direction, source distance, aperture and physical/display units require explicit tests. The existing approximate optical model ignores stripe width and cannot predict the new line process's efficiency without calibration.

Normalize each direction safely; reject impossible propagation directions before sqrt; use finite zero spectral RGB for zero XYZ, then apply any selected preset's appearance fallback; guard chromaticity intersection denominators and initialize fallback candidates. Keep parameter data away from display transfer functions. Specify whether output is linear RGB or display sRGB and apply the chosen output conversion exactly once. Preserve the legacy display mode for comparison.

## 6. Performance design and projections

Let N=H*W, A=active cells, K=unique geometry keys, and L≈pitch/period stripes per cell. Decode/filter costs are O(N) for fixed filter kernels. Reused cell construction is O(K*L), placement/export O(A); no flattening into A*L paths. A geometry cache key includes period, pitch, layer, dose, grid and exposure mode, but excludes placement angle because SREF rotates the cell. For common legacy settings K≤31; RGB16 supports more distinct periods, so bound/cache/report K rather than assume 31 universally.

The 2.254-million-pixel sample implies approximately 343.4 MiB of old VBO storage and 1.386 billion spectral order/wavelength checks per full frame. Instancing cuts storage but does not by itself remove the spectral computation. Four-corner exact mode at full coverage remains expensive. At one evaluation per cell, the same sample still requires about 347 million checks/frame. At 60 Hz that is about 20.8 billion checks/second, so a universal 60 FPS promise would be unjustified.

Plan compact design arrays (roughly 13 bytes/pixel for uint32 period, float64 angle, bool mask, before RGB and workspaces), compact instance buffers (target 16–24 bytes/active cell), bounded tiling, viewport culling, and optional preview LOD with visible labels. Optional float32 fallback data adds 4 bytes/pixel and appearance assets/staging add their own storage; include them, snapshots, decoder/filter temporaries and diagnostics in peak-memory measurements. Do not retain duplicate full grids or Python objects for every placement. Bound filter temporary arrays via halo tiles; Gaussian/bilateral edges must equal the untiled implementation. Export runs outside the UI loop with coarse progress messages and bounded chunks, without pickling/copying the entire layout per message.

A rotated SREF is approximately 60–100 bytes depending on name and emitted records, so 2.254 million placements imply roughly 135–225 MB of uncompressed hierarchy before headers. A two-endpoint path occupies 48 bytes with PATH/LAYER/DATATYPE/WIDTH/XY/ENDEL, versus 64 bytes for the legacy four-corner closed BOUNDARY. Cell definitions remain small when K is small, so this primitive change barely reduces a reference-dominated file. Measure the actual writer. AREF compression is a future extension and cannot be assumed in initial file-size projections.

Provisional engineering targets, not measured promises: interactive fast preview ≤33 ms median / ≤50 ms p95 on the recorded reference GPU at 1280×720 using a stated visible-sample cap; event/cancel response ≤100 ms; 2.254-million-cell export ≤60 s and ≤1 GiB peak host memory on the recorded workstation with diagnostics disabled and streaming text output. Target compact device buffers below 256 MiB for that sample. Exact mode is benchmarked independently with no unverified 30/60 FPS requirement. If targets fail, profile before changing algorithms; never silently reduce exported resolution or spectral fidelity.

Benchmark sizes 1, 256², 512², 1024² and 1878×1200; masks at 0/10/50/100% activity; K=1/31/301 and custom palette worst cases; filtering on/off; both optical orders presets. Record GPU/CPU/driver/GL/Python/dependency versions, RAM/VRAM, warm/cold timings, frame-time distributions, file bytes, active count and accuracy mode. Report decode, filter, geometry, upload, render, GDS and text IO separately. Include cancellation, oversized inputs and memory-bound behavior.

## 7. Delivery phases and exit gates

| Phase | Deliverables | Required exit evidence | Indicative effort |
|---|---|---|---|
| 0 — Freeze evidence | Source/asset hashes, isolated original dependency environment, fixtures, chosen workstation; original GDS generated from shared example | Reproducible original outputs or specifically documented external baseline gap; MATLAB fixture runner prepared | 2–4 developer days |
| 1 — Shared model and RGB | Codec profiles, schemas, grid, legacy migration, operations, project persistence | F01–F06; all channel codes, exact round trips, no cross-channel conversion, mask and coordinate fixtures | 4–6 days |
| 2 — Raith minimum port | Binary records, DF, zero-width path/SREF, structures/library, streaming export, holopixels | F13–F15; MATLAB-generated line fixtures, independent path readback, no grating BOUNDARY records, rejection tests | 5–8 days |
| 3 — Shared preview | CPU optical oracle, GPU triangles/instances, source presets, geometry view, mesh/material utilities | F08–F12; CPU/GPU tolerances, finite-output and orientation tests, full border coverage | 5–8 days |
| 4 — Combined workflows | API/CLI, plots, text exports, immutable jobs, progress, examples and migration docs | F07, F16–F19; end-to-end preview/export identity and no-write behavior | 3–5 days |
| 5 — Qualification | Performance tuning, install/package checks, full regression matrix, Raith import validation | All F01–F19 closed; benchmark report; actual NanoSuite import verified | 3–5 days |

Total planning estimate: 22–36 focused developer days for one experienced developer, excluding waiting for MATLAB/NanoSuite access and experimental optical calibration. Binary interoperability and renderer correctness are the largest uncertainties. Phases 2 and 3 can be developed independently after phase 1 freezes its interface, but the plan does not require additional agents to do implementation.

Tests compare contracts, geometry and numerical outputs, rather than duplicating implementation. Enumerate RGB8 channel codes and RGB16 codes independently; test cross-channel independence with adversarial triples, byte order, metadata/gamma chunks, nearest resampling, and inactive data. Test angles at 0/±45/±90, asymmetric masks, pitch/period boundary values, and odd image shapes. GPU tests compare linear XYZ/RGB with float64 CPU outputs on non-boundary cases (initial tolerance 1e−5 absolute + 1e−4 relative); aperture threshold cases need separate inside/outside fixtures and a declared epsilon, not a hidden loose screenshot tolerance.

GDS comparisons normalize timestamps only and compare record semantics, hierarchy, path endpoints, WIDTH=0, reference transforms, layer, dose and units. Independently transform small fixtures' paths without polygonizing them. Assert no BOUNDARY grating records, no connectors between stripes, and no automatic path widening. Compare new centerlines with the centerlines derived from the original gdsfactory rectangle fixtures after the agreed 1 nm snap; polygon area equivalence is deliberately not a criterion after the user's primitive change. Keep large regression tests hierarchical. Each documented correction gets an explicit expected-difference fixture.

## 8. Release conditions and external dependencies

The plan can be implemented without further clarification by using the stated defaults. Remaining external evidence is clearly gated:

- MATLAB-generated fixtures must validate the translated writer against the pinned upstream implementation. An independently installed reader validates ordinary GDS; it does not prove NanoSuite interpretation.
- Native `.csf` compatibility requires actual target NanoSuite import validation; record version, units, line-exposure mode/dose, hierarchy and transforms. No hardware exposure is part of software testing. Without that access, mark native qualification pending and do not call it fabrication-ready.
- The missing original dependency versions make exact baseline reproducibility uncertain; preserve source-equivalent parameter/geometry fixtures and report any version-dependent differences.
- RGB channel conventions are proposed engineering choices, since the request did not assign R/G/B meanings. They are versioned so a later different assignment is an importer change, not a redesign.

Completion means every feature ID has an implemented acceptance result or an explicit user-approved scope change; no missing base functionality is hidden under “future Raith work.” Unsupported Raith features remain explicitly unavailable until their separate ports and fixtures are complete.
