"""Compare the accelerated preview with the CPU spectral reference."""

import time
import tkinter as tk
from queue import Queue
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from dot_ebl_preview.core.encoding import RGB8IndexedProfile
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.gui import DesignWindow
from dot_ebl_preview.gui_logic import SceneSettings, render_scene, render_scene_gpu
from dot_ebl_preview.preview.gl_renderer import ReusableGLRenderer
from dot_ebl_preview.preview.realtime import EventQueue, FramePayload, RealtimeViewer


def test_opengl_preview_matches_cpu_for_positions_orientation_and_fallback():
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")
    shape = (6, 6)
    periods = np.tile(np.array([900, 950, 1000, 1050, 1100, 1150], dtype=np.uint32), (6, 1))
    angles = np.zeros(shape, dtype=np.float64)
    angles[:, 2] = 4.0
    angles[:, 3] = -4.0
    active = np.ones(shape, dtype=bool)
    active[0, 0] = False
    fallback = np.zeros(shape, dtype=np.float32)
    fallback[0, 0] = 0.2
    design = Design(shape=shape, pitch_nm=20000, period_nm=periods,
                    angle_deg=angles, active=active, fallback_intensity=fallback)
    scene = SceneSettings(light_pos=(0.0, 20.6487533, 29.4891314),
                          camera_pos=(0.3, 0.0, 66.0), orientation_deg=2.0,
                          aperture_mm=5.0, source_size_mm=0.0)

    try:
        gpu = np.asarray(render_scene_gpu(design, scene), dtype=np.int16)
    except RuntimeError as error:
        if "unavailable" in str(error) or "could not initialize" in str(error):
            pytest.skip(str(error))
        raise
    cpu = np.asarray(render_scene(design, scene), dtype=np.int16)

    assert gpu.shape == cpu.shape == (6, 6, 3)
    assert int(cpu.max()) > 20
    assert np.max(np.abs(gpu - cpu)) <= 4
    assert gpu[0, 0].tolist() == [51, 51, 51]


def test_gui_preview_button_runs_opengl_in_worker(monkeypatch):
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Desktop session unavailable: {error}")
    root.withdraw()
    window = None
    try:
        window = DesignWindow(root)
        window.design = Design(
            shape=(1, 1), pitch_nm=20000,
            period_nm=np.array([[1000]], dtype=np.uint32),
            angle_deg=np.array([[0.0]]), active=np.array([[True]]),
        )
        monkeypatch.setattr("tkinter.messagebox.showerror", lambda *args, **kwargs: pytest.fail(str(args)))
        window._preview()
        deadline = time.monotonic() + 10
        while (window.preview_running or window.preview_image is None) and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        root.update()
        assert not window.preview_running
        assert window.preview_image is not None
        assert window.preview_image.size == (1, 1)
        assert window.panel_images["preview"] is window.preview_image
        assert all(window.panel_images[key] is None for key in ("source", "periods", "angles"))
        assert "OpenGL (fast) preview updated" in window.status_var.get()
    finally:
        if window is not None:
            window._close()
        else:
            root.destroy()


def test_live_slider_keeps_latest_scene_without_blocking_controls(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Desktop session unavailable: {error}")
    root.withdraw()
    window = None
    viewers = []

    class FakeViewer:
        def __init__(self, _design, settings, visible=True):
            self.scenes = [settings]
            self.events = Queue()
            self.serial = 0
            self.closed = False
            self.visible = visible
            self.orbits = []
            viewers.append(self)

        def start(self):
            pass

        def update_scene(self, settings):
            self.scenes.append(settings)
            self.serial += 1

        def close(self):
            self.closed = True

        def capture(self, token):
            self.events.put(("capture", (token, Image.new("RGB", (1, 1), (60, 0, 0)))))

        def orbit(self, which, **kwargs):
            self.orbits.append((which, kwargs))

    try:
        monkeypatch.setattr("dot_ebl_preview.gui.RealtimeViewer", FakeViewer)
        window = DesignWindow(root)
        window.design = Design(
            shape=(1, 1), pitch_nm=20000,
            period_nm=np.array([[1000]], dtype=np.uint32),
            angle_deg=np.array([[0.0]]), active=np.array([[True]]),
        )
        window._scene_changed()
        assert len(viewers) == 1
        assert viewers[0].visible is False
        assert all(button.instate(["!disabled"]) for button in window.action_buttons)

        window.point_sliders["Illumination"][0].set(1.0)
        window.point_sliders["Illumination"][0].set(2.0)
        window.point_sliders["Illumination"][0].set(3.0)
        root.update()
        assert float(window.source_vars["x"].get()) == pytest.approx(3.0)
        assert viewers[0].scenes[-1].light_pos[0] == pytest.approx(3.0)
        assert window.preview_pending is None
        assert not window.preview_running

        viewers[0].events.put(("frame", (viewers[0].serial, Image.new("RGB", (1, 1), (60, 0, 0)))))
        window._poll_viewer_events()
        assert window.preview_image.getpixel((0, 0)) == (60, 0, 0)
        assert window.panel_images["preview"].getpixel((0, 0)) == (60, 0, 0)

        window._preview_drag_start(SimpleNamespace(x=10, y=10), 1)
        window._preview_drag_move(SimpleNamespace(x=20, y=5), 1)
        window._preview_drag_end(SimpleNamespace())
        window._preview_wheel(SimpleNamespace(delta=120, state=1))
        assert viewers[0].orbits == [
            ("camera", {"delta_az": 3.5, "delta_el": 1.75}),
            ("light", {"distance_factor": 0.9}),
        ]

        scene = SceneSettings(light_pos=(5.0, 20.6487533, 29.4891314))
        newer_scene = SceneSettings(light_pos=(6.0, 20.6487533, 29.4891314))
        count_before = len(viewers[0].scenes)
        viewers[0].events.put(("scene", scene))
        viewers[0].events.put(("scene", newer_scene))
        window._poll_viewer_events()
        assert float(window.source_vars["x"].get()) == pytest.approx(6.0)
        assert len(viewers[0].scenes) == count_before

        before_switch = window._point(window.source_vars)
        window.live_var.set(False)
        window._live_toggled()
        assert viewers[0].closed
        window.source_vars["mode"].set("Direction")
        assert window._point(window.source_vars) == pytest.approx(before_switch, abs=1e-3)
    finally:
        if window is not None:
            window._close()
        else:
            root.destroy()


def test_gui_displays_source_periods_angles_and_live_frame_together(monkeypatch, tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Desktop session unavailable: {error}")
    root.withdraw()
    window = None
    viewers = []

    class FakeViewer:
        def __init__(self, _design, _settings, visible=True):
            self.events = Queue()
            self.serial = 0
            self.visible = visible
            viewers.append(self)

        def start(self):
            pass

        def update_scene(self, _settings):
            self.serial += 1

        def close(self):
            pass

    design = Design(
        shape=(2, 2), pitch_nm=20000,
        period_nm=np.array([[900, 1000], [1100, 1000]], dtype=np.uint32),
        angle_deg=np.array([[0, 45], [-30, 45]], dtype=np.float64),
        active=np.ones((2, 2), dtype=bool),
    )
    encoded, _ = RGB8IndexedProfile().encode(design)
    source_path = tmp_path / "original.png"
    Image.fromarray(encoded, mode="RGB").save(source_path)

    try:
        monkeypatch.setattr("dot_ebl_preview.gui.RealtimeViewer", FakeViewer)
        window = DesignWindow(root)
        window.path_var.set(str(source_path))
        window.format_var.set("RGB8 indexed")
        window._load()
        deadline = time.monotonic() + 5
        while window.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        root.update()
        assert not window.busy
        assert set(window.panel_canvases) == {"source", "periods", "angles", "preview"}
        assert np.array_equal(np.asarray(window.panel_images["source"]), encoded)
        assert window.panel_images["periods"].size == (2, 2)
        assert window.panel_images["angles"].size == (2, 2)
        assert window.panel_images["preview"] is None
        assert len(viewers) == 1 and viewers[0].visible is False

        viewers[0].events.put(("frame", (0, Image.new("RGB", (2, 2), (12, 34, 56)))))
        window._poll_viewer_events()
        assert window.panel_images["preview"].getpixel((0, 0)) == (12, 34, 56)
        assert np.array_equal(np.asarray(window.panel_images["source"]), encoded)
    finally:
        if window is not None:
            window._close()
        else:
            root.destroy()


def test_realtime_viewer_reuses_context_and_captures_current_frame():
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")
    design = Design(
        shape=(8, 8), pitch_nm=20000,
        period_nm=np.full((8, 8), 1000, dtype=np.uint32),
        angle_deg=np.zeros((8, 8)), active=np.ones((8, 8), dtype=bool),
    )
    viewer = RealtimeViewer(design, SceneSettings(), visible=False)
    viewer.start()
    try:
        deadline = time.monotonic() + 10
        initial = None
        while time.monotonic() < deadline:
            kind, payload = viewer.events.get(timeout=1)
            if kind == "error":
                pytest.fail(str(payload))
            if kind == "frame":
                initial = payload
                break
        assert initial is not None and initial[0] == 0
        assert initial[1].size == (8, 8)

        viewer.update_scene(SceneSettings(light_pos=(1.0, 20.6487533, 29.4891314)))
        viewer.capture(42)
        captured = None
        while time.monotonic() < deadline:
            kind, payload = viewer.events.get(timeout=1)
            if kind == "error":
                pytest.fail(str(payload))
            if kind == "capture" and payload[0] == 42:
                captured = payload[1]
                break
        assert captured is not None and captured.size == (8, 8)
        assert viewer.is_alive
    finally:
        viewer.close()
    assert not viewer.is_alive


def test_realtime_viewer_publishes_latest_fast_frame_after_rapid_change():
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")
    size = 512
    design = Design(
        shape=(size, size), pitch_nm=20000,
        period_nm=np.full((size, size), 1000, dtype=np.uint32),
        angle_deg=np.zeros((size, size)), active=np.ones((size, size), dtype=bool),
    )
    viewer = RealtimeViewer(design, SceneSettings(), visible=False)
    viewer.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            kind, payload = viewer.events.get(timeout=1)
            if kind == "error":
                pytest.fail(str(payload))
            if kind == "frame":
                assert payload[1].size == (384, 384)
                break
        else:
            pytest.fail("Initial fast frame did not arrive")

        viewer.update_scene(SceneSettings(light_pos=(1.0, 20.6487533, 29.4891314)))
        while time.monotonic() < deadline:
            kind, payload = viewer.events.get(timeout=1)
            if kind == "error":
                pytest.fail(str(payload))
            if kind == "frame" and payload[0] == viewer.serial:
                assert payload[1].size == (384, 384)
                break
        else:
            pytest.fail("Updated fast frame did not arrive")
    finally:
        viewer.close()


def test_event_queue_mailbox_coalesces_frames():
    queue = EventQueue()
    queue.put(("opened", None))
    img1 = Image.new("RGB", (10, 10), (1, 1, 1))
    img2 = Image.new("RGB", (10, 10), (2, 2, 2))
    img3 = Image.new("RGB", (10, 10), (3, 3, 3))
    queue.put(("frame", FramePayload(1, img1, quality=0)))
    queue.put(("frame", FramePayload(2, img2, quality=0)))
    queue.put(("frame", FramePayload(3, img3, quality=1)))
    queue.put(("scene", SceneSettings()))

    kind1, payload1 = queue.get_nowait()
    assert kind1 == "opened"
    kind2, payload2 = queue.get_nowait()
    assert kind2 == "frame"
    assert payload2[0] == 3
    assert payload2[1] is img3
    assert payload2.quality == 1
    kind3, payload3 = queue.get_nowait()
    assert kind3 == "scene"
    assert queue.empty()


def test_monotonic_frame_acceptance_and_quality_upgrade(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Desktop session unavailable: {error}")
    root.withdraw()
    window = None
    try:
        window = DesignWindow(root)
        viewer = SimpleNamespace(events=Queue(), serial=5)
        window.viewer = viewer

        img_fast1 = Image.new("RGB", (1, 1), (10, 0, 0))
        img_fast2 = Image.new("RGB", (1, 1), (20, 0, 0))
        img_stale = Image.new("RGB", (1, 1), (5, 0, 0))
        img_settled2 = Image.new("RGB", (1, 1), (25, 0, 0))

        viewer.events.put(("frame", FramePayload(1, img_fast1, quality=0)))
        window._poll_viewer_events()
        assert window.preview_image.getpixel((0, 0)) == (10, 0, 0)
        assert window._last_displayed_serial == 1
        assert window._last_displayed_quality == 0

        viewer.events.put(("frame", FramePayload(0, img_stale, quality=1)))
        window._poll_viewer_events()
        assert window.preview_image.getpixel((0, 0)) == (10, 0, 0)
        assert window._last_displayed_serial == 1

        viewer.events.put(("frame", FramePayload(2, img_fast2, quality=0)))
        window._poll_viewer_events()
        assert window.preview_image.getpixel((0, 0)) == (20, 0, 0)
        assert window._last_displayed_serial == 2
        assert window._last_displayed_quality == 0

        viewer.events.put(("frame", FramePayload(2, img_settled2, quality=1)))
        window._poll_viewer_events()
        assert window.preview_image.getpixel((0, 0)) == (25, 0, 0)
        assert window._last_displayed_serial == 2
        assert window._last_displayed_quality == 1
    finally:
        if window is not None:
            window._close()
        else:
            root.destroy()


def test_reusable_gl_renderer_caches_and_reuses_textures():
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")
    renderer = ReusableGLRenderer()
    try:
        shape = (4, 4)
        design1 = Design(
            shape=shape, pitch_nm=20000,
            period_nm=np.full(shape, 1000, dtype=np.uint32),
            angle_deg=np.zeros(shape), active=np.ones(shape, dtype=bool),
        )
        img1 = renderer.render(design1, (0, 20, 30), (0, 0, 66), 0.0)
        assert img1.size == (4, 4)
        hash1 = renderer.design_hash
        tex1 = renderer.data_texture
        prog1 = renderer.program

        img2 = renderer.render(design1, (0, 25, 30), (0, 0, 66), 1.0)
        assert img2.size == (4, 4)
        assert renderer.design_hash == hash1
        assert renderer.data_texture == tex1
        assert renderer.program == prog1

        design2 = Design(
            shape=shape, pitch_nm=20000,
            period_nm=np.full(shape, 1200, dtype=np.uint32),
            angle_deg=np.zeros(shape), active=np.ones(shape, dtype=bool),
        )
        img3 = renderer.render(design2, (0, 25, 30), (0, 0, 66), 1.0)
        assert img3.size == (4, 4)
        assert renderer.design_hash != hash1
        assert renderer.program == prog1
    finally:
        renderer.close()


def test_realtime_viewer_settled_pane_size_and_capture_resolution():
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")
    size = 512
    design = Design(
        shape=(size, size), pitch_nm=20000,
        period_nm=np.full((size, size), 1000, dtype=np.uint32),
        angle_deg=np.zeros((size, size)), active=np.ones((size, size), dtype=bool),
    )
    viewer = RealtimeViewer(design, SceneSettings(), visible=False, pane_size=(384, 384))
    viewer.start()
    try:
        deadline = time.monotonic() + 10
        fast_frame = None
        settled_frame = None
        while time.monotonic() < deadline:
            kind, payload = viewer.events.get(timeout=1)
            if kind == "error":
                pytest.fail(str(payload))
            if kind == "frame":
                if payload.quality == 0 and fast_frame is None:
                    fast_frame = payload
                elif payload.quality == 1:
                    settled_frame = payload
                    break
        assert fast_frame is not None
        assert fast_frame[1].size == (384, 384)
        assert settled_frame is not None
        assert settled_frame[1].size == (384, 384)
        assert settled_frame.quality == 1

        viewer.capture(99)
        captured = None
        while time.monotonic() < deadline:
            kind, payload = viewer.events.get(timeout=1)
            if kind == "error":
                pytest.fail(str(payload))
            if kind == "capture" and payload[0] == 99:
                captured = payload[1]
                break
        assert captured is not None
        assert captured.size == (size, size)
    finally:
        viewer.close()


def test_continuous_input_acceptance_without_frame_drops():
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")
    shape = (16, 16)
    design = Design(
        shape=shape, pitch_nm=20000,
        period_nm=np.full(shape, 1000, dtype=np.uint32),
        angle_deg=np.zeros(shape), active=np.ones(shape, dtype=bool),
    )
    viewer = RealtimeViewer(design, SceneSettings(), visible=False)
    viewer.start()
    displayed = []
    last_serial = -1
    last_quality = -1
    try:
        for i in range(15):
            viewer.update_scene(SceneSettings(orientation_deg=float(i)))
            time.sleep(0.005)
            while True:
                try:
                    kind, payload = viewer.events.get_nowait()
                except Exception:
                    break
                if kind == "frame":
                    serial = payload[0]
                    quality = getattr(payload, "quality", 0)
                    if serial > last_serial or (serial == last_serial and quality > last_quality):
                        displayed.append(serial)
                        last_serial = serial
                        last_quality = quality

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(displayed) < 5:
            try:
                kind, payload = viewer.events.get(timeout=0.1)
            except Exception:
                continue
            if kind == "frame":
                serial = payload[0]
                quality = getattr(payload, "quality", 0)
                if serial > last_serial or (serial == last_serial and quality > last_quality):
                    displayed.append(serial)
                    last_serial = serial
                    last_quality = quality

        assert len(displayed) >= 3
        for a, b in zip(displayed, displayed[1:]):
            assert a <= b
    finally:
        viewer.close()
