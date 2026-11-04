# Agent Guide — Dot-Matrix EBL Preview & Fabrication Platform

This document provides essential context and instructions for AI coding agents working on `dot-ebl-preview`.

---

## Architecture Knowledge Base

Before making structural changes, consult the comprehensive architectural specifications in `docs/architecture/`:

- **[Master Index](file:///docs/architecture/INDEX.md)**: Overview of all technical documentation.
- **[01 — System Overview](file:///docs/architecture/01_SYSTEM_OVERVIEW.md)**: Platforms (Web & Python), directory structure, dataflow.
- **[02 — Core Data Model & Codecs](file:///docs/architecture/02_CORE_DATA_MODEL_AND_CODECS.md)**: `Design` / `DesignModel`, coordinates, quantization, RGBA continuous, HLS, HSV, NPZ.
- **[03 — Optical Diffraction Physics](file:///docs/architecture/03_OPTICAL_DIFFRACTION_PHYSICS.md)**: 77-band CIE 1931 D65 diffraction equations, nickel reflectance, finite source/detector convolutions, guarded sRGB gamut mapping, WebGL2 shaders.
- **[04 — Raith EBL Fabrication Engine](file:///docs/architecture/04_RAITH_EBL_FABRICATION_ENGINE.md)**: Single-pixel `WIDTH=0` paths, circular aperture chords, hierarchical SREF structures, binary GDSII Stream Release 3 format, export bundles.
- **[05 — Web Application Frontend Architecture](file:///docs/architecture/05_WEB_APPLICATION_ARCHITECTURE.md)**: SPA component tree, `designStore`, `sceneStore`, FlatView & PerspectiveView viewports, Web Workers (`designWorker`, `fabricationWorker`).
- **[06 — Desktop GUI & CLI](file:///docs/architecture/06_DESKTOP_GUI_AND_CLI.md)**: Python Tkinter 4-pane desktop GUI, PyInstaller executable build, PyOpenGL realtime viewer, CLI commands, Python programmatic API.
- **[07 — Testing & Development Guide](file:///docs/architecture/07_TESTING_AND_DEVELOPMENT_GUIDE.md)**: Vitest unit tests, Playwright browser test invariants, optical parity thresholds, dev server and build commands.

---

## Key Invariants for Agents

1. **Physical Quantization**:
   - All spatial distances, lattice pitches, and grating periods are strictly integer nanometres (`np.uint32` / `Uint32Array`).
   - Angles are 64-bit IEEE floating-point degrees (`np.float64` / `Float64Array`) bounded in $[-90.0^\circ, +90.0^\circ]$.
   - Always use half-away-from-zero rounding:
     $$\text{round}(x) = \begin{cases} \lfloor x + 0.5 \rfloor & \text{if } x \ge 0 \\ \lceil x - 0.5 \rceil & \text{if } x < 0 \end{cases}$$

2. **Single-Pixel Exposure Geometry**:
   - Hologram cells are circular apertures of diameter equal to cell pitch ($D = P$).
   - Grating lines are emitted as zero-width paths (`PATH` records with `WIDTH = 0 nm`).
   - Area-dose filled polygons are strictly prohibited.

3. **Browser Testing Invariants**:
   - In `web/tests/browser/welcome_and_navigation.spec.ts` line 11, the suite verifies:
     `await expect(presetCards).toHaveCount(4);`
   - In `web/tests/browser/audit_regressions.spec.ts` line 52:
     `for (let i = 0; i < 4; i++)`
   - When introducing showcase holograms or presets, either maintain the 4-card physical benchmark count or update test assertions intentionally.

4. **Common Commands**:
   - Type check: `cd web; npm run check`
   - Build web bundle: `cd web; npm run build`
   - Unit tests: `cd web; npm test`
   - Playwright browser tests: `cd web; npm run test:browser`
