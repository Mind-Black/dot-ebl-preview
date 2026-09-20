"""Entry point for PyInstaller and direct desktop launches."""

import sys

from dot_ebl_preview.gui import main


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        import tkinter as tk
        from dot_ebl_preview.gui import DesignWindow

        root = tk.Tk()
        root.withdraw()
        window = DesignWindow(root)
        root.update()
        assert set(window.panel_canvases) == {"source", "periods", "angles", "preview"}
        window._close()
    elif sys.argv[1:] == ["--gpu-self-test"]:
        import numpy as np
        from dot_ebl_preview.core.model import Design
        from dot_ebl_preview.gui_logic import SceneSettings, render_scene_gpu

        design = Design(
            shape=(1, 1), pitch_nm=20000,
            period_nm=np.array([[1000]], dtype=np.uint32),
            angle_deg=np.array([[0.0]]), active=np.array([[True]]),
        )
        image = render_scene_gpu(design, SceneSettings())
        assert image.size == (1, 1)
        assert max(image.getpixel((0, 0))) > 0
    elif sys.argv[1:] == ["--realtime-self-test"]:
        import time
        import numpy as np
        from dot_ebl_preview.core.model import Design
        from dot_ebl_preview.gui_logic import SceneSettings
        from dot_ebl_preview.preview.realtime import RealtimeViewer

        design = Design(
            shape=(1, 1), pitch_nm=20000,
            period_nm=np.array([[1000]], dtype=np.uint32),
            angle_deg=np.array([[0.0]]), active=np.array([[True]]),
        )
        viewer = RealtimeViewer(design, SceneSettings(), visible=False)
        viewer.start()
        try:
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                kind, payload = viewer.events.get(timeout=1.0)
                if kind == "error":
                    raise RuntimeError(payload)
                if kind == "frame":
                    assert payload[1].size == (1, 1)
                    break
            else:
                raise TimeoutError("Live OpenGL viewer did not render a frame.")
        finally:
            viewer.close()
    else:
        main()
