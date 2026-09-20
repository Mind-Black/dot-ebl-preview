# Source audit and feature coverage

Inspected 2026-09-20. Source baselines:

- `learning-shaders`: `b747079257ab662e4869af72701ff78c8688db39`.
- `Holtida-EBL`: `1cf838cd221f41cb2ac6d47f5e4f80c655a3b131`.
- Both working trees were clean when inspected. No applicable `AGENTS.md` was found in the project trees or inspected ancestor directories. The destination was initially empty.

All Python source files, active GLSL, the archived Unity shader, and the OBJ sample were inspected. Image metadata was inspected for all 13 PNG assets. [SOURCE_MANIFEST.json](SOURCE_MANIFEST.json) records hashes and sizes of all 27 base-project files plus the five pinned upstream files. All five Python files passed AST parsing. Executing only the pure NumPy table module confirmed the four spectral tables have 77 wavelength samples, premultiplied XYZ has shape (77,3), and the calibration arrays have eight entries. No application/GUI/GDS pipeline was executed. The available bundled Python has NumPy and Pillow but lacks OpenCV, SciPy, pygame, PyOpenGL, pyrr, gdsfactory, and Matplotlib. MATLAB/Octave were not found on PATH. Neither repository supplies a dependency lock, tests, or a README. Holtida's ignored `_INPUT` and `_OUTPUT` directories are absent.

## 1. learning-shaders data flow

`main.py:11` starts pygame/OpenGL at 640 × 480, enables depth/blending, compiles GLSL 330, uploads spectral tables, creates a mesh, and loads `gfx/dog2.png`. The mesh actually uses `images/amt_design_01.png` regardless of the arguments to `make_hologram_mesh` (`main.py:190`). The dog texture is bound but not sampled by the active fragment shader.

`load_image.py:9` loads BGR with OpenCV, converts to HLS, promotes hue to int16 and doubles it to even values 0–358, and normalizes saturation and lightness to 0–100. `create_angles_gratings` (`:71`) indexes a 360-entry 0.9–1.2 µm period table and rounds periods to 0.01 µm. Angles start as `(saturation - 50) / 100 * angle_range`; the method defaults to 180°, but the active app passes 90°. Hue 162 is overwritten with `-5 + 25 * distance/max_dist`, using center `(width//2, height//2 + 50)` in pixels. The code writes invalid sentinels, applies an unconditional Gaussian filter with sigma 1, and converts periods from µm to metres.

`create_meshgrid` (`:64`) uses 60 µm pixel spacing in the active app and centers the grid. The mesh reverses Y; it creates four vertices, each containing position, UV, normal, period and angle (10 float32 values). Grid arrays have W and H entries, and loops stop at W−1 and H−1: the final image row and column are omitted. Mesh generation uses a large Python list and then creates the float32 upload buffer.

The animation rotates the Euler-angle vector around Z by 0.02 radians per frame, maintaining a tilt magnitude of 4 degrees; this is not simply a rigid body spin around Z. Each frame builds model matrices, draws `GL_QUADS`, and caps the loop at 60 Hz. Only closing the window is handled; mouse orbit and parameter editing are not existing functionality.

`shaders/vertex.txt` calculates spectral diffraction per vertex: wavelengths 380–760 nm in 5 nm steps (77 samples), nonzero orders −1 and +1, nickel reflectance multiplied by a standard illuminant and XYZ color matching data. Source and camera are hardcoded; aperture acceptance uses `5 / camera_distance`. It normalizes XYZ, maps chromaticities toward the illuminant white point into an RGB triangle, and converts XYZ to RGB. The fragment shader simply displays the interpolated vertex color. This is an approximate optical visualization, without a rigorous electromagnetic solver or calibrated intensity model.

`load_tables.py` provides XYZ/RGB conversion and primaries, four spectral arrays, premultiplication, and dormant eight-period laser calibration tables. Preserve every table and its provenance. `specIntens()` exists but the active path uses `stdIllum()`.

The imported Unity shader is not launched by this Python project. It contains additional capabilities: texture→HSV→nearest calibrated period, rejection below saturation 0.1, hue >0.7 mapped to the first period, configurable min/max angle (default −10/+10°), source/camera transforms, aperture, orders ±1 and ±2 (second orders weighted 1/15), different illuminant normalization, and dim grayscale fallback when diffraction is dark. Preserve its applicable algorithms as explicit compatibility presets, with RGB parameters replacing HSV decoding. Unity integration itself is a reference asset, not a working second application in this repository.

## 2. Holtida-EBL data flow

`main.py:54` exposes `dot_matrix_hologram(name, image, px_size=20, write=False, downscale_factor=1, rotation_filter=False)`. It reads `_INPUT/<image>`, performs OpenCV BGR→HLS conversion, and optionally downsamples each HLS channel with nearest-neighbor interpolation to floor(W/factor) × floor(H/factor).

Hue selects the same rounded 0.9–1.2 µm period table. Raw lightness 0 or 255 makes a pixel inactive. Saturation maps to −90..+90 degrees, rounded to whole degrees before other operations. Hue 162 activates `-15 + 40 * distance/max_dist`, with the same 50-pixel center offset. Optional bilateral filtering uses diameter 3, sigmaColor 10, sigmaSpace 100. Masking occurs after bilateral filtering. Periods and angles are plotted alongside HLS diagnostics; `plt.show()` blocks even when export is requested.

`create_holopixel` (`main.py:33`) generates horizontal rectangles of width 0.1 µm. At y = −size/2 + period/2 + k*period, the half-length is sqrt((size/2)^2 − y^2); y outside the radius is discarded. These are circular-envelope chord rectangles, not perfectly circle-clipped stripes: rectangle corners can lie outside the nominal circle. The user's follow-up explicitly replaces these rectangles with Raith single-pixel lines; preserve each rectangle's chord centerline/phase, not its area or width.

Export builds one child structure per unique valid period, places references rotated by the angle at `(column*size + size/2, -(row*size + size/2))`, wraps the hologram in a named top structure, and writes timestamped GDS plus `angles.txt` and `gratings.txt`. The layer/datatype pair is `(1, 1000)`. `write=True` returns the top component; `write=False` plots and returns None. Progress/elapsed time/ETA exist in `resources/ProgressBar.py`, though placement progress is commented out and the cell-building denominator prevents reaching 100%.

## 3. Inconsistencies to resolve explicitly

| Issue | Evidence | Planned treatment |
|---|---|---|
| HLS parameter conversion loses information and couples channels | Both loaders use 8-bit OpenCV HLS | Direct RGB numeric channels; explicit one-time legacy importer |
| Physical pitch mismatch | 60 µm preview, 20 µm EBL | One shared pitch; named source presets retain both |
| Different angle/radial/filter behavior | ±45° active preview versus ±90° export; distinct radial ranges; Gaussian versus optional bilateral | Preserve selectable recipes; preview and export always consume the same chosen result |
| White not masked in preview | Lightness normalized to 100, then compared with 255 | Correct activity mask; document visual difference |
| Invalid angle −1000 spreads into neighbors | Preview filters after sentinel assignment | Separate mask; normalize valid-only filter weights |
| Filter wrap and masked-neighbor effects | Both use ordinary scalar smoothing | Keep scalar filter compatibility modes; add explicit axial/circular mode, never silently replace a recipe |
| Dropped last row/column and tiny-image failure | Mesh loops over coordinate arrays minus one | Build W+1/H+1 edges or use instances; include every pixel |
| Core-profile incompatibility | GLSL 330 core with GL_QUADS | Indexed triangles |
| Incorrect normal transform | Normal has homogeneous w=1, so translation affects it | Inverse-transpose normal transform, w=0 |
| Undefined shader results | Zero XYZ sum, negative sqrt argument, parallel line intersections, uninitialized gamut candidates | Guard and validate finite results; stable gamut fallback |
| EBL/preview orientation may disagree | EBL positive rotation gives normal (−sin θ, cos θ); shader uses (+sin θ, cos θ) and signed diffraction coordinates | Define and test one convention using asymmetric patterns and an analytic orientation reference |
| Camera/projection mismatch and mixed scene scales | Projection implicitly views from origin; optical camera at z=66; image dimensions in metres | Explicit view matrix and dimensioned scene settings; compatibility preset isolated |
| Coefficients and normalization differ | GLSL coefficient shadowed/unused, order ±2 branch unreachable; Unity uses coefficient and unreflected light normalization | Preserve source optical presets; corrected default must be independently specified/tested |
| Fragile paths/names/outputs | CWD-relative assets, minute timestamp at import, period-only cell names | Explicit paths, collision-resistant names, per-export timestamps and manifest |
| No reproducible original GDS baseline yet | gdsfactory version absent; no generated files supplied | Freeze an isolated legacy environment and archive fixtures during implementation phase 0 |

## 4. Feature migration matrix

Each ID is a release acceptance item, not merely a code-moving task. “Reference” means the functionality is present in code but dormant in the supplied executable path.

| ID | Source capability | Destination | Acceptance evidence |
|---|---|---|---|
| F01 | PNG/BMP loading and missing-file errors | `io/images`, `io/legacy_hls` | Byte fixtures, missing/invalid input tests |
| F02 | Period/angle/mask extraction, uniqueness diagnostics | `core/encoding`, diagnostics | All RGB codes tested; legacy parameter fixtures |
| F03 | Pixel pitch, physical extents, centers/edges | `core/grid` | 1×1, 1×N, N×1, asymmetric 2×3, all corners |
| F04 | Nearest-neighbor downscale | `core/resample` | Odd dimensions, excessive/invalid factor, coordinate convention |
| F05 | Both radial overrides | `core/operations` | Both formulas and center offsets; explicit region selection |
| F06 | Gaussian and bilateral smoothing | `core/filters` | Isolated mask edge, constant field, wrap-boundary fixtures |
| F07 | Source/channel/period/angle plots and unique values | `diagnostics` | RGB + physical maps; HLS plots only for legacy diagnostics |
| F08 | Spectral arrays, primaries, conversions, laser tables | `optics/tables` | Shapes, values, checksums, array ordering |
| F09 | Spectral preview, aperture, gamut mapping | `optics`, `preview` | CPU/GPU numerical comparisons and finite-output edge cases |
| F10 | Automatic tilt animation, perspective, quit/cleanup | `preview/app` | Time-based equivalent motion, resource lifecycle smoke test |
| F11 | OBJ parsing/triangulation, transforms, texture material (reference) | `preview/mesh`, `preview/material` | Cube renders with correct independent vertex layout; texture diagnostic mode |
| F12 | Unity calibration, ±2 orders, angle range, grayscale fallback (reference) | `optics/presets`, separate HSV legacy importer, independent appearance field | Eight calibrated periods; saturation/hue/tie thresholds; source-mean/5 fallback and intensity cutoff fixtures |
| F13 | Circular-envelope grating stripes; polygons/width explicitly replaced by user's follow-up | `layout/holopixel` with separate zero-width paths | Match original stripe centerlines; WIDTH=0, no grating BOUNDARY or inter-stripe connectors; degenerate-line diagnostics |
| F14 | Reused period cells, rotation, XY placement, top wrapper | `layout/hologram`, `raith` | Hierarchy, placements, transformed geometry, names |
| F15 | Layer/datatype 1/1000; GDS generation | `raith/writer` | Independent reader + MATLAB writer fixtures; DF 1→1000 |
| F16 | Text parameter outputs and timestamp folders | `io/exports` | Units, row order, inactive sentinels and reload checks |
| F17 | Progress, elapsed time, ETA | `jobs/progress` | Empty/single/many pixel runs, completion and cancellation |
| F18 | Callable generation and write/no-write workflows | Public Python API + CLI | No-write creates no layout file; explicit return contract; export returns layout/result |
| F19 | All sample images, dog textures, OBJ and shader references | `examples`, provenance manifest | Asset hashes; explicit legacy import labels |

Retaining functionality does not mean keeping gdsfactory's `Component` type, accidental NaNs, incorrect masks, or invisible test textures in the normal preview. API changes and corrected outputs must be documented. The explicit polygon→single-pixel-line change supersedes preserving finite stripe width/area. No other active base capability is assigned to a future release; only unrelated Raith toolbox features are deferred.

## 5. Dataset and performance facts

The primary example is 1878 × 1200 = 2,253,600 pixels. Other design images are 250², 500² (three), 600², 1024² (two), 1075², and 224 × 256; two RGBA dog textures are 1024². Image dimensions were read with Pillow; HLS distributions were not measured.

At full coverage, the old mesh represents 1877 × 1199 = 2,250,523 cells, with 9,002,092 vertices and a 360,083,680-byte float32 VBO, excluding the much larger transient Python list. At 154 wavelength/order checks per vertex, that is approximately 1.386 billion acceptance checks per frame before overhead. These are source-derived operation counts, not measured frame times. The original default image is already large enough that performance must be part of the architecture.
