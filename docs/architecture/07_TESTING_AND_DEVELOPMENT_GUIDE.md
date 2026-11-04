# 07 — Testing, Quality Assurance & Development Guide

## Testing Philosophy

`dot-ebl-preview` enforces end-to-end parity between mathematical specifications, Python reference code, and the TypeScript WebGL2 web platform. Any change to optical mathematics, coordinate handling, or GDSII serialization must pass cross-language validation suites.

---

## 1. Web Test Suites (`web/tests/`)

The web platform maintains two distinct test layers:

### Unit Tests (Vitest)
Location: `web/tests/unit/`
- Command: `cd web; npm test` (or `npx vitest run`)
- Suites:
  - `decoders.test.ts`: Validates image decoders against reference fixture outputs (`hls_expected.json`, `unity_expected.json`, `rgb8_expected.json`, `rgb16_expected.json`).
  - `rgbaContinuous.test.ts`: Exhaustive test of 16-bit period and 8-bit angle quantization, clamping, and edge cases.
  - `optics.test.ts`: Verifies spectral table interpolation, coordinate transformations, and colorimetry.
  - `store.test.ts`: Tests reactive subscriptions, state isolation, and history.
  - `liveDesign.test.ts`: Verifies dynamic parameter edits and filter applications.
  - `fabrication.test.ts`: Validates chord math, datatype conversions, and GDSII binary serialization parity with Python reference fixtures (`raith.json`).

### Browser Integration Tests (Playwright)
Location: `web/tests/browser/`
- Command: `cd web; npm run test:browser` (or `npx playwright test`)
- Headless Chromium with real WebGL2 rendering:
  - `welcome_and_navigation.spec.ts`: Tests welcome landing view, dropzone, preset cards count (4 cards), and responsive mobile collapse.
  - `live_preview.spec.ts`: Verifies live WebGL2 texture swapping and optical re-rendering during user interactions.
  - `optics_shader_readback.spec.ts`: Reads back rendered WebGL2 canvas pixels and asserts parity with Python CPU reference outputs within 4 code values per channel (under `optical_reference_expected.json`).
  - `fabrication_export.spec.ts`: Validates asynchronous Web Worker GDSII snapshot generation, download triggers, and million-cell performance.
  - `audit_regressions.spec.ts`: Tests keyboard accessibility, dialog traps, error recovery when WebGL is denied or files are corrupted, and layout bounding boxes across 5 display resolutions ($1440\times900$, $1280\times720$, $768\times1024$, $390\times844$, $720\times450$).
  - `production_bundle.spec.ts`: Validates production asset loading and relative path handling.

---

## 2. Python Test Suite (`tests/`)

Location: `tests/`
- Command: `pytest`
- Key test modules:
  - `test_gl_preview.py`: Headless OpenGL context rendering tests.
  - `test_multi_light.py`: Additive spectral superposition tests across 1 to 8 light sources.
  - `test_gui_logic.py`: Desktop GUI state transitions, parameter tables, and coordinate mappings.
  - `test_rgba_continuous.py`: Python codec profile verification.

---

## 3. Development Workflow & Commands

### Running the Web Platform
```powershell
cd web
npm ci                # Install locked dependencies
npm run dev           # Start Vite local development server at http://localhost:3000
npm run check         # Run TypeScript typecheck (tsc -b)
npm test              # Run unit tests (vitest)
npm run test:browser  # Run Playwright browser tests
npm run build         # Build production bundle into web/dist
```

### Building the Desktop Executable
```powershell
# From workspace root
.\.venv\Scripts\python.exe -m pip install -e ".[gui,gui-build]"
.\build_gui.ps1
# Output binary: dist\DotEBLPreview.exe
```

---

## 4. Critical Invariants to Respect

When contributing or refactoring:

1. **Preset Count in Tests**:
   - `welcome_and_navigation.spec.ts` line 11 checks:
     `await expect(presetCards).toHaveCount(4);`
   - `audit_regressions.spec.ts` line 52 loops over:
     `for (let i = 0; i < 4; i++)`
   - If adding new default presets or showcase designs, ensure tests are either updated intentionally or the showcase design is integrated via a dedicated showcase banner/button without breaking the 4 core benchmark assertions.

2. **Optical Parity Threshold**:
   - WebGL2 and Python CPU reference readbacks must agree within 4 code values (out of 255) per color channel (`optics_shader_readback.spec.ts`). Do not modify spectral weights or color matching curves without regenerating corresponding test fixtures (`tools/web/generate_fixtures.py`).

3. **Deterministic Rounding**:
   - Always use half-away-from-zero rounding for coordinate and parameter quantization. Never use standard `Math.round` or Python's default round-to-even `round()` when calculating physical integers.
