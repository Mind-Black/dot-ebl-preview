# Independent Critic review

Reviewed 2026-09-20 by a separate professional-developer Critic subagent. This review evaluates the initial `DEVELOPMENT_PLAN.md`, `SOURCE_AUDIT.md`, and `RAITH_PORT.md`, before the author's response. It is a source and architecture review, not runtime qualification.

**Verdict: the architecture is feasible and the feature inventory is substantially complete. Accept the direction with the required amendments below. Do not declare complete functionality preservation until R1 is resolved, or deterministic fabrication semantics until R2 and R3 are resolved.** No fundamental rewrite of the plan is necessary.

I independently read both projects' Python source, active GLSL, the Unity reference shader, spectral/calibration tables, and the relevant pinned MATLAB element validation, hierarchy, record encoder, PATH and SREF writer branches. I checked the supplied OBJ format. I did not execute OpenGL, gdsfactory, MATLAB, or NanoSuite, and did not measure performance.

## Required amendments, ranked by severity

### R1 — P1: Unity fallback and HSV migration lack the data needed for promised fidelity

**Evidence:** `learning-shaders/shaders/imported_holo-app/HologramShader.shader:441–481` uses its own RGB→HSV algorithm, saturation `<0.1` rejection, hue `>0.7` selection, nearest calibrated hue with first-entry tie behavior, and saturation-based angle mapping. At lines 588–603, if no RGB output component exceeds `0.01`, its displayed grayscale is `(source_R + source_G + source_B) / 15`. This depends on the original appearance RGB, not just the resulting period, angle and activity.

The plan promises these capabilities in F12, but the explicit importer contract only names the original HLS mappings. The authoritative Design contains period, angle, activity and provenance, without an appearance/fallback field. RGB parameter B is strictly activity. Two legacy source colors can yield identical physical parameters but different fallback brightness, so a physical-parameter-only artifact cannot reproduce the promised behavior. The general instruction to return black for zero XYZ also needs an exception for this preset.

**Required correction:**

- Name a third migration mode, `legacy-unity-hsv`, distinct from both OpenCV HLS importers. Reproduce the shader's `rgb2hsv` and selection comparisons, including strict threshold boundaries and first-index ties. New RGB parameter imports still use no HSV conversion.
- Preserve an optional `appearance_rgb` or `fallback_gray` field independently of parameter channels, with source sampling, numeric range, color-space interpretation and provenance declared. Include it in project persistence and the preview snapshot hash. A derived fallback field stores the shader's mean source RGB divided by five; retaining the original source image is also acceptable if reconstruction/sampling is deterministic.
- For the Unity optical preset, select fallback after finite spectral/gamut processing when all RGB channels are `<=0.01`; zero diffraction reaches that fallback. Declare the corrected behavior for grating-zero/inactive samples because the original divides by zero before reaching undefined arithmetic. A reasonable explicit rule is no diffraction plus retained grayscale context, with activity continuing to exclude fabrication.
- For new parameter-only designs, use a documented default fallback intensity or a separate appearance input. Never infer brightness by averaging encoded parameter R/G/B values.
- Add fixtures with equal decoded period/angle but different source brightness, HSV saturation immediately below/at/above `0.1`, hue around `0.7`, nearest-hue ties, threshold RGB around `0.01`, and project save/reload.

**Gate:** blocks F12 closure and a claim that all promised reference functionality is preserved. It does not block starting the core or Raith port.

### R2 — P2: Axial smoothing can alter finite stripe phase through an implicit 180° branch choice

**Evidence:** `Holtida-EBL/main.py:35` begins the stripe lattice at `-size/2 + period/2`. This finite chord set is generally not invariant under 180° rotation. For 20,000 nm pitch and 900 nm period, its 22 stripe centers run from −9,550 to +9,350 nm. A 180° rotation produces centers from −9,350 to +9,550 nm: parallel orientation, different exposure positions. The plan's doubled-angle smoothing intentionally identifies angles modulo 180°, but does not specify how to recover the directed SREF angle after filtering.

**Required correction:** retain the directed placement angle. After doubled-angle smoothing, lift the axial result to the branch nearest the original cell's directed angle, with deterministic ties and a defined policy if the selected profile cannot represent that branch. Do not automatically normalize all stored/exported angles to a principal 180° interval or deduplicate cells by axial angle. Report any deliberate 180° branch change as a geometry/phase change. Keep scalar source presets unchanged. A future phase-aware orientation model may change this contract, but is not needed initially.

Add fixtures around −90/+90 degrees using a non-centrosymmetric stripe lattice; compare transformed path coordinates, not only grating normals or optical colors. Include the exact 20,000/900 nm example above. The existing near-zero-resultant fallback remains necessary but does not solve this branch issue.

**Gate:** blocks exposing axial smoothing as a defined fabrication operation. The default unfiltered and scalar compatibility recipes remain implementable.

### R3 — P2: Lossy RGB8 export needs an explicit selection and error contract

**Evidence:** The plan correctly prevents silent RGB16 quantization and keeps processed designs in typed arrays. RGB8 tables can represent exact discrete palettes, but filtered/radial angles can fall outside their tables. It says deliberate RGB export produces an error report without specifying RGB8 nearest-entry selection, ties, or the error metric. For example, `0.5°` lies halfway between the default `0°` and `1°` entries. Applying axial distance to select an endpoint can additionally cause R2's geometry change.

**Required correction:** make exact representability the default for every parameter-image export. For RGB8, `reject` requires each active physical value to match an allowed table entry under the declared numeric representation. Explicit `quantize` selects the nearest entry in physical units; use directed angle distance by default and a stable tie rule such as lowest table index. Reject out-of-range values unless an independently explicit clipping policy is selected. Record maximum/RMS period and angle errors, changed active-pixel counts, chosen entries/policy, and any phase-changing branch choice. Export then decode the image for verification before publishing it. Do not overwrite the authoritative Design as a side effect of interchange export.

**Gate:** blocks advertising deterministic quantized RGB8 export. Lossless imports and exact palette exports are unaffected.

## Smaller corrections and useful implementation constraints

### R4 — P3: Test half-grid stripe centers even with an even pixel pitch

The plan calls out half-grid placement centers for odd pitch. Local stripe centers also land on half-nanometres when period is odd, including the retained 903 nm calibrated period at the normal 20,000 nm pitch. MATLAB-style half-away-from-zero rounding can create a one-nanometre spacing difference across zero. The planned one-time endpoint snapping is appropriate; add this specific fixture and report local spacing/phase deviation separately from placement and rotation error. This is a test refinement, not a new architectural dependency.

### R5 — P3: Publish multi-file exports as a coherent bundle

The export consists of GDS/CSF, two text maps, a design artifact and manifest, but the atomic-write sentence describes one temporary file. Stage a complete export directory on the same filesystem, write the manifest only after all checks succeed, and publish that directory (or use a final completion marker). A cancelled or failed job must not leave a seemingly completed GDS paired with missing/stale parameter maps. Add interruption tests between files. This improves workflow integrity without changing the requested design functionality.

## Functionality and translation assessment

- Active Python capability coverage is strong: both parameter mappings, both radial formulas, nearest downscale, Gaussian/bilateral options, physical pitch/placement, diagnostics, spectral tables, animation, cleanup, hierarchical export, text arrays, timestamps and progress all have destination entries. Existing bugs are identified explicitly rather than silently carried forward.
- The dormant OBJ parser/material utilities and Unity algorithm differences are included. R1 closes the substantive data-model gap found in that reference coverage. Restoring a Unity application is appropriately outside a Python combination project; the supplied Unity file alone is not such an application.
- The user's polygon replacement is correctly interpreted. Upstream `Raith_library.m:702` emits PATH, explicit WIDTH=0 and two XY vertices. Separate chords avoid unintended connecting exposures. This is not a Raith dot primitive, and no filled polygon is needed in the initial grating implementation.
- The initial Raith dependency closure is proportionate: element validation, named structures/library, transforms, PATH/SREF serialization, units, real8 encoding and DF→DATATYPE. Reflection/magnification support is a small, useful foundation even though the current layouts use only rotation/translation.
- The deferred inventory keeps all other toolbox element families, text, hierarchy plotting and position lists available as pinned source with extension points. It satisfies future translation availability without claiming those ports already exist. Retaining independent native/plain conversion registries is the right boundary.
- MPL/source provenance is addressed and the production writer is required to use the translated serializer. A mature GDS reader remains independent validation tooling, not a disguised replacement layout engine.

## Performance and feasibility assessment

The projected cost model is substantially correct. The original 2,253,600-pixel image creates roughly nine million vertices and a 344 MiB VBO before its Python list overhead. Four-corner spectral evaluation costs roughly 1.386 billion order/wavelength checks per full frame. Instancing reduces storage, but does not erase those checks. The plan correctly refuses to guarantee full-resolution real-time exact rendering.

The 13-byte/pixel authoritative-array estimate is credible as a payload estimate, not total working memory. Memory accounting must also include optional R1 appearance data, image decoding, masks, filter halos, immutable snapshots, CPU/GPU staging, diagnostics and placement chunks. At roughly 2.25 million active references, accidentally constructing a Python object per placement would threaten the 1 GiB goal; the plan explicitly prohibits this and should retain that constraint in implementation review.

Hierarchical geometry costs `O(K*L + A)` rather than flattening `A*L` line primitives. A two-endpoint PATH is 48 bytes under the pinned writer, and a closed four-corner BOUNDARY is 64 bytes; the reported 135–225 MB SREF-dominated export projection is a defensible planning range. Switching polygon primitives to lines will not yield a proportionate whole-file size reduction.

The 33 ms fast-preview target, 60-second large export target and 1 GiB host-memory target are engineering objectives, not evidenced performance. A measured visible-sample budget and error comparison are needed before promising them. The 22–36 developer-day estimate is plausible for an experienced developer with prompt access to required tooling, but uncertain for the new optical reference, native interoperability and all reference-feature fixtures. Keep external access wait time separate and revise estimates after phases 0–2.

## Existing release blockers that the plan correctly preserves

These are not defects in the plan, and cannot be closed by this review:

1. The translated serializer needs actual pinned-MATLAB fixtures plus independent record/readback checks, including signed coordinates, real8, dose boundaries, nonzero rotations, and WIDTH=0.
2. NanoSuite must verify line-mode and dose interpretation. DF=1 and DATATYPE=1000 do not establish equivalent developed linewidth or a transferable polygon area-dose recipe.
3. The source applications and proposed renderer have not been benchmarked here. CPU/GPU numerical parity and baseline screenshots are implementation evidence still to obtain.
4. Physical optical accuracy for the new single-pixel-line process needs calibration; the existing approximate model cannot establish diffraction efficiency or developed feature width.

With R1–R3 incorporated, the plan is a sound basis for implementation. R4–R5 should be added to the acceptance checklist. This review does not authorize or claim application implementation, runtime compatibility, or fabrication readiness.

## Second pass — 2026-09-20

I reviewed the revised plan, updated F12 coverage and `REVIEW_RESPONSE.md`, limited to the five findings above. **R1–R5 are closed at the planning level. The revised plan is approved as a basis for implementation.**

- R1 now specifies the separate Unity HSV migration, persisted independent appearance/fallback information, threshold/tie semantics, corrected inactive behavior and required fixtures. It also appropriately identifies the missing Unity runtime color/sampling configuration as an evidence limitation.
- R2 now preserves directed rotations, specifies nearest-original axial branches and deterministic ties, rejects out-of-range results instead of silently wrapping, and tests actual asymmetric line coordinates.
- R3 now defines exact-first RGB8 export, physical-unit distances, directed-angle handling, index-based tie resolution, explicit clipping, error reporting and decode verification without mutating the Design.
- R4 includes the 903 nm period half-grid fixture and separates local geometry deviations from placement/transform errors.
- R5 now publishes a staged, verified export bundle with completion metadata and interruption tests. Additional appearance memory is included in the performance accounting.

No remaining contradiction was found within this bounded second pass. Closure means the specifications and acceptance requirements address the findings; no implementation or runtime test result is implied. The original assessment and external qualification gates above remain intact.
