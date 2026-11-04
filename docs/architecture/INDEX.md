# Dot-EBL Preview — Architecture & Codebase Knowledge Base

This documentation suite serves as the single source of truth for the architecture, physical models, fabrication engines, and implementation details of `dot-ebl-preview`.

---

## Documentation Suite

| Document | Topic | Key Contents |
| :--- | :--- | :--- |
| **[01 — System Overview](file:///docs/architecture/01_SYSTEM_OVERVIEW.md)** | Architecture & Platforms | System purpose, dual platform (Web & Python), directory structure, end-to-end dataflow. |
| **[02 — Core Data Model & Codecs](file:///docs/architecture/02_CORE_DATA_MODEL_AND_CODECS.md)** | Physical Design & Interchange | `Design` / `DesignModel`, integer nanometre quantization, coordinate spaces, RGBA continuous, HLS, HSV, NPZ. |
| **[03 — Optical Diffraction Physics](file:///docs/architecture/03_OPTICAL_DIFFRACTION_PHYSICS.md)** | Optical Simulation & Shaders | 77-band CIE 1931 D65 diffraction equations, nickel reflectance, finite source/detector convolutions, guarded sRGB gamut mapping, WebGL2 shaders. |
| **[04 — Raith EBL Fabrication](file:///docs/architecture/04_RAITH_EBL_FABRICATION_ENGINE.md)** | EBL Lithography & GDSII | Single-pixel `WIDTH=0` paths, circular aperture chords, hierarchical `SREF` structures, binary GDSII Stream Release 3 format, export bundles. |
| **[05 — Web Frontend Architecture](file:///docs/architecture/05_WEB_APPLICATION_ARCHITECTURE.md)** | Web Application & UI | SPA component tree, `designStore`, `sceneStore`, FlatView & PerspectiveView viewports, Web Workers (`designWorker`, `fabricationWorker`). |
| **[06 — Desktop GUI & CLI](file:///docs/architecture/06_DESKTOP_GUI_AND_CLI.md)** | Python Desktop & Shell Tools | Tkinter 4-pane desktop GUI, PyInstaller executable build, PyOpenGL realtime viewer, CLI commands, Python programmatic API. |
| **[07 — Testing & Development](file:///docs/architecture/07_TESTING_AND_DEVELOPMENT_GUIDE.md)** | QA & Development Guide | Vitest unit tests, Playwright browser test invariants, optical parity thresholds, dev server and build commands. |

---

## Quick Technology Reference

- **Physical Units**: Integer nanometres (`uint32`) for period and lattice pitch ($20,000\,\text{nm} = 20\,\mu\text{m}$); degrees (`float64`) for rotation $[-90^\circ, +90^\circ]$.
- **Web Stack**: TypeScript, Vite 6, WebGL2 (GLSL ES 3.00), Canvas 2D, Vitest 2, Playwright. Zero backend dependencies.
- **Python Stack**: Python 3.10+, NumPy, Pillow, Tkinter, PyOpenGL, GLFW, PyInstaller.
- **Fabrication Standard**: Pure-Python and Web Worker GDSII Stream Release 3 serializer matching University of Alberta nanoFAB `Raith_GDSII` toolbox. Single-pixel circular aperture chords.
