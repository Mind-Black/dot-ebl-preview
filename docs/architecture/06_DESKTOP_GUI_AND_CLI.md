# 06 — Desktop GUI, CLI & Python API

## Overview

In addition to the Web platform, `dot-ebl-preview` provides a native desktop interface and terminal tooling implemented in Python 3.10+. This allows local batch processing, automated scripting, and workstation execution without a web browser.

---

## 1. Desktop GUI (`src/dot_ebl_preview/gui.py`)

The desktop GUI is built with Python's standard `tkinter` / `ttk` library and designed for responsiveness during heavy image processing and OpenGL rendering:

```
+---------------------------------------------------------------------------------------+
|  Dot EBL Preview — Desktop Workbench                                                   |
+-------------------------------------------+-------------------------------------------+
|  [Source RGB File Pane]                   |  [Period Map Pane]                        |
|  Displays original input RGB/PNG/BMP      |  Pseudocolor mapping of grating periods   |
|                                           |                                           |
+-------------------------------------------+-------------------------------------------+
|  [Angle Map Pane]                         |  [Live Diffraction Preview Pane]          |
|  Pseudocolor mapping of rotation angles   |  Interactive OpenGL 3.3 preview frame     |
|                                           |                                           |
+-------------------------------------------+-------------------------------------------+
|  Controls: File Ingestion | Parameters | Illumination & Observer | Fabrication Export |
+---------------------------------------------------------------------------------------+
```

### Key Subsystems:
1. **Threaded Execution (`ThreadPoolExecutor`)**:
   - Long-running tasks (file importing, CPU diffraction fallback, GDSII file saving) run in a dedicated background worker thread (`max_workers=1`).
   - Results are dispatched back to the Tkinter event loop via thread-safe queues (`self.results = Queue()`) polled by `root.after()`.

2. **Realtime OpenGL Preview Viewer (`RealtimeViewer`)**:
   - File: `src/dot_ebl_preview/preview/realtime.py`.
   - Spawns an isolated GLFW/PyOpenGL rendering context to prevent OpenGL state pollution inside the main UI process.
   - Communicates frame buffer captures and mouse orbital events across process boundaries.

3. **Standalone Executable Distribution**:
   - Built using PyInstaller via `DotEBLPreview.spec` and `build_gui.ps1`:
     ```powershell
     .\.venv\Scripts\python.exe -m pip install -e ".[gui,gui-build]"
     .\build_gui.ps1
     ```
   - Bundles Python, Tkinter, NumPy, Pillow, and OpenGL dependencies into a single portable binary: `dist\DotEBLPreview.exe`.

---

## 2. Command Line Interface (`dot-ebl`)

File: `src/dot_ebl_preview/cli.py`

The CLI exposes complete design ingestion, optical rendering, and GDSII generation workflows for shell scripting and CI/CD pipelines.

### Primary Subcommands:

1. **`import-legacy`**:
   Converts legacy OpenCV HLS or Unity HSV parameter images into canonical `design.npz` archives:
   ```bash
   dot-ebl import-legacy input.bmp --preset holtida-ebl --mode corrected -o design.npz
   ```

2. **`preview`**:
   Renders a calibrated optical diffraction PNG snapshot from a design archive:
   ```bash
   dot-ebl preview design.npz -o preview.png --preset corrected --light "0,230,328,20,1.0"
   ```

3. **`export-gds`**:
   Generates a hierarchical Raith GDSII binary from a design archive:
   ```bash
   dot-ebl export-gds design.npz -o layout.gds --layer 1 --dose 1.0
   ```

4. **`export-bundle`**:
   Generates a complete fabrication bundle with GDSII, coordinate lists, NPZ, PNG, and SHA-256 verification manifest:
   ```bash
   dot-ebl export-bundle design.npz -o ./_OUTPUT --layout-name SHOWCASE
   ```

5. **`inspect`**:
   Outputs tabular summaries of active cells, unique grating periods, and angle distributions.

---

## 3. Programmatic Python API (`src/dot_ebl_preview/api.py`)

Python scripts and automated workflows can import high-level functions directly:

```python
from dot_ebl_preview.api import (
    load_design,
    render_preview_image,
    render_preview_to_file,
    export_bundle,
    save_gds,
    import_legacy_hls,
)

# 1. Load canonical design
design = load_design("design.npz")

# 2. Render optical diffraction preview (returns PIL Image)
image = render_preview_image(design, preset="corrected")
image.save("preview.png")

# 3. Export complete fabrication bundle
bundle_dir = export_bundle(
    design,
    output_dir="./_OUTPUT",
    layout_name="EXPERIMENT_01",
    layer=1,
)
print(f"Exported bundle to: {bundle_dir}")
```
