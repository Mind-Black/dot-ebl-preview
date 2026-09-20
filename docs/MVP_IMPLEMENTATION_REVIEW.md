# MVP implementation review

Date: 2026-09-20  
Reviewed commit: `dae416a` — initial MVP implementation of dot-ebl-preview

## Assessment

Five bugs were confirmed in the initial MVP implementation. The existing test suite passes, but focused probes expose gaps in export preservation, legacy preset defaults, optical positioning, RGB16 quantization, and preview color conversion.

This was a code and runtime review. No implementation fixes were made.

## Findings

### 1. [P1] Preserve existing bundles on timestamp collisions

Location: `src/dot_ebl_preview/jobs/bundle.py:128–130`

Two exports with the same layout name within one second resolve to the same output directory. The second export recursively deletes the first completed bundle before publishing its replacement.

**Reproduction:** Freeze the timestamp, export a design, add a marker file inside its bundle, then export a changed design with the same name. Both calls return the same directory, and the marker disappears.

**Impact:** An export can silently destroy an earlier completed output. Deleting the destination before renaming also leaves a window where neither completed bundle is available.

**Recommended fix:** Generate unique output directories or reject collisions without deleting previous exports. Use uniquely allocated staging directories as well.

**Regression coverage:** Export different designs under the same name and timestamp; verify the first completed bundle remains intact.

### 2. [P1] Preserve each legacy preset's default pitch

Location: `src/dot_ebl_preview/cli.py:96–100`; argument default at line 60

The CLI always supplies a 20 µm pitch to legacy importers, overriding the 60 µm defaults for `learning-shaders` and `unity-hsv` even when the user does not specify `--pitch-um`.

**Reproduction:** Import the same image using the Python API with `preset="learning-shaders"` and the CLI with `--preset learning-shaders`. The API produces `pitch_nm=60000`; the CLI artifact contains `pitch_nm=20000`.

**Impact:** CLI-imported fabrication dimensions shrink threefold relative to the preset's default, and holopixel geometry changes with the pitch.

**Recommended fix:** Apply a pitch override only when `--pitch-um` is explicitly supplied; otherwise preserve the selected importer's default.

**Regression coverage:** Compare API and CLI default pitches for every legacy preset, and verify explicit pitch overrides still work.

### 3. [P2] Evaluate optics at each cell's physical position

Location: `src/dot_ebl_preview/optics/engine.py:274–277`

The full-design renderer calls `simulate_cell_optical_color()` without `world_pos`, so every cell is evaluated at `(0, 0, 0)`. Its cache considers only period and rounded angle. Cell location and design pitch therefore cannot affect the preview, despite the optical model using finite camera and light positions.

**Reproduction:** Instrument simulation calls while rendering a uniform 2×2 design. Only one origin position is evaluated. Separately, the single-cell simulator with period 1000 nm and angle 0° returns approximately `(1.0, 0.52035, 0.0)` at `(0, 0, 0)` and black at `(10, 0, 0)` under the default parameters, demonstrating position sensitivity in the underlying model.

**Impact:** The preview omits spatial changes in diffraction across the physical design.

**Recommended fix:** Pass centered physical cell coordinates with explicit conversion to the camera/light coordinate units. Include position in caching, or use another evaluation strategy that preserves the spatial dependence.

**Regression coverage:** Use a uniform grating over a finite extent and compare full-design output against independent per-cell calls at the corresponding positions. Include a pitch-change case.

### 4. [P2] Round signed angles before adding the RGB16 offset

Location: `src/dot_ebl_preview/core/encoding.py:372–373`

The encoder adds 32768 before applying half-away-from-zero rounding. This changes the tie direction for negative half-step angles and violates the documented formula `round(angle × scale) + offset`.

**Reproduction:** Encode −0.005° using `RGB16FixedProfile.encode(..., policy="quantize")`, then decode. The result is 0°; the documented contract requires −0.01°.

**Impact:** Negative half-step angles receive different codes from the specified interchange contract.

**Recommended fix:** Round the signed scaled angle first, then add the offset and validate the resulting code range.

**Regression coverage:** Check positive and negative half-step ties, including ±0.005°, along with representable boundary values.

### 5. [P2] Convert linear RGB to display sRGB before saving previews

Location: `src/dot_ebl_preview/preview/renderer.py:23–26`

The optical engine returns linear RGB, but the PNG renderer scales those values directly to bytes without applying the display transfer function.

**Reproduction:** Supply a linear RGB value of 0.25 to the PNG conversion path. The saved channel value is 64; sRGB encoding produces approximately 137.

**Impact:** Corrected previews appear too dark when displayed as ordinary sRGB images.

**Recommended fix:** Define the output color-space contract and apply the sRGB transfer function exactly once for corrected previews. Keep any intentional legacy display behavior explicit. Account for the interpretation of stored fallback intensities when defining this contract.

**Regression coverage:** Verify known linear-to-sRGB values, including the transfer-function breakpoint, and ensure fallback intensities are not converted twice.

## Verification and limits

- Existing suite: **123 passed** using `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`.
- Five focused review probes failed their expected-correctness assertions, confirming the five findings above.
- An additional OpenCV hue-boundary probe was skipped because OpenCV was unavailable in the project environment. It is not reported as a confirmed finding.
- Temporary review probes were removed; the working tree was clean at the end of the review.
- MATLAB/NanoSuite interoperability, hardware exposure behavior, GPU parity, and large-design performance were not qualified by this review.

P1 denotes a high-priority correctness or data-loss issue. P2 denotes a correctness issue that should be fixed in the normal development cycle.
