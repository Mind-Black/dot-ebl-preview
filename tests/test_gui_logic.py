"""GUI workflow tests without creating a desktop window."""

from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from dot_ebl_preview.core.encoding import RGB8IndexedProfile
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.gui_logic import (
    SceneSettings, direction_from_position, load_gui_design, parameter_counts, parameter_map,
    position_from_direction, render_scene, save_gds,
)


def test_load_counts_and_maps_use_active_cells(tmp_path):
    original = Design(
        shape=(2, 3), pitch_nm=20000,
        period_nm=np.array([[900, 1000, 0], [1000, 1100, 0]], dtype=np.uint32),
        angle_deg=np.array([[0, 45, 0], [45, -30, 0]], dtype=np.float64),
        active=np.array([[True, True, False], [True, True, False]]),
    )
    path = tmp_path / "encoded.png"
    encoded, _ = RGB8IndexedProfile().encode(original)
    Image.fromarray(encoded, mode="RGB").save(path)

    design = load_gui_design(path, "RGB8 indexed", 20)
    assert parameter_counts(design, "gratings") == [(0.9, 1), (1.0, 2), (1.1, 1)]
    assert parameter_counts(design, "angles") == [(-30.0, 1), (0.0, 1), (45.0, 2)]
    for kind in ("gratings", "angles"):
        image = parameter_map(design, kind)
        assert image.size == (3, 2)
        assert image.getpixel((2, 0)) == (24, 24, 24)
        assert image.getpixel((0, 0)) != image.getpixel((1, 0))


def test_direction_coordinates_and_preview_settings_reach_renderer(monkeypatch):
    design = Design(
        shape=(1, 1), pitch_nm=20000,
        period_nm=np.array([[1000]], dtype=np.uint32),
        angle_deg=np.array([[20.0]]), active=np.array([[True]]),
    )
    seen = {}

    def fake_render(rotated, preset, params):
        seen.update(angle=float(rotated.angle_deg[0, 0]), preset=preset,
                    light=params.light_pos, camera=params.camera_pos)
        return Image.new("RGB", (1, 1))

    monkeypatch.setattr("dot_ebl_preview.gui_logic.render_preview_image", fake_render)
    light = position_from_direction(90, 0, 25)
    settings = SceneSettings(light_pos=light, camera_pos=(1, 2, 66), orientation_deg=30)
    render_scene(design, settings)
    assert seen["angle"] == 50.0
    assert seen["light"] == pytest.approx((0, 25, 0), abs=1e-10)
    assert seen["camera"] == (1, 2, 66)
    assert seen["preset"] == "corrected"
    with pytest.raises(ValueError):
        position_from_direction(0, 91, 10)
    assert position_from_direction(*direction_from_position((3, 4, 12))) == pytest.approx((3, 4, 12))


def test_save_gds_creates_file_without_touching_design(tmp_path):
    design = Design(
        shape=(1, 1), pitch_nm=20000,
        period_nm=np.array([[1000]], dtype=np.uint32),
        angle_deg=np.array([[0.0]]), active=np.array([[True]]),
    )
    original_hash = design.content_hash()
    path = save_gds(design, tmp_path / "sample.gds")
    assert path.exists() and path.stat().st_size > 100
    assert path.read_bytes()[:4] == b"\x00\x06\x00\x02"
    assert design.content_hash() == original_hash
    assert list(tmp_path.iterdir()) == [path]


def test_opencv_hls_to_rgb_roundtrip():
    from dot_ebl_preview.gui_logic import opencv_hls_to_rgb
    from dot_ebl_preview.io.legacy_hls import rgb_to_opencv_hls

    rgb = np.array([[[255, 0, 0], [0, 255, 0]], [[0, 0, 255], [128, 128, 128]]], dtype=np.uint8)
    h, l, s = rgb_to_opencv_hls(rgb)
    reconstructed = opencv_hls_to_rgb(h, l, s)
    assert np.max(np.abs(rgb.astype(int) - reconstructed.astype(int))) <= 2


def test_unity_hsv_to_rgb():
    from dot_ebl_preview.gui_logic import unity_hsv_to_rgb
    from dot_ebl_preview.io.legacy_unity import shader_rgb_to_hsv

    h = np.array([[0.1, 0.5]], dtype=np.float32)
    s = np.array([[0.8, 0.5]], dtype=np.float32)
    v = np.array([[1.0, 0.7]], dtype=np.float32)
    rgb = unity_hsv_to_rgb(h, s, v)
    assert rgb.shape == (1, 2, 3)
    assert rgb.dtype == np.uint8

    r0, g0, b0 = rgb[0, 0] / 255.0
    rec_h, rec_s, rec_v = shader_rgb_to_hsv(r0, g0, b0)
    assert rec_h == pytest.approx(0.1, abs=0.01)
    assert rec_s == pytest.approx(0.8, abs=0.01)


def test_apply_parameter_edit():
    from dot_ebl_preview.gui_logic import apply_parameter_edit

    design = Design(
        shape=(2, 2), pitch_nm=20000,
        period_nm=np.array([[900, 1000], [1000, 1100]], dtype=np.uint32),
        angle_deg=np.array([[0.0, 45.0], [45.0, -30.0]], dtype=np.float64),
        active=np.array([[True, True], [True, True]]),
    )

    # Edit grating 1.0 -> 1.05
    d_mod, count = apply_parameter_edit(design, "gratings", 1.0, 1.05)
    assert count == 2
    assert np.all(d_mod.period_nm == np.array([[900, 1050], [1050, 1100]]))

    # Edit angle 45.0 -> 50.0
    d_mod, count_a = apply_parameter_edit(d_mod, "angles", 45.0, 50.0)
    assert count_a == 2
    assert np.allclose(d_mod.angle_deg, np.array([[0.0, 50.0], [50.0, -30.0]]))

    # Invalid inputs
    with pytest.raises(ValueError):
        apply_parameter_edit(design, "gratings", 1.05, -0.5)
    with pytest.raises(ValueError):
        apply_parameter_edit(design, "gratings", 1.05, 0.0)
    with pytest.raises(ValueError):
        apply_parameter_edit(design, "angles", 50.0, float("nan"))


def test_encode_gui_design_image_all_formats():
    from dot_ebl_preview.gui_logic import encode_gui_design_image

    design = Design(
        shape=(2, 2), pitch_nm=20000,
        period_nm=np.array([[950, 1050], [1150, 0]], dtype=np.uint32),
        angle_deg=np.array([[0.0, 30.0], [-45.0, 0.0]], dtype=np.float64),
        active=np.array([[True, True], [True, False]]),
    )

    for fmt in ("RGB8 indexed", "RGB16 fixed", "Holtida legacy HLS", "Learning Shaders HLS", "Unity HSV"):
        raw, img = encode_gui_design_image(design, fmt)
        assert raw.shape[:2] == (2, 2)
        assert img.size == (2, 2)


def test_save_gui_design_image_and_export_bundle(tmp_path):
    from dot_ebl_preview.gui_logic import (
        encode_gui_design_image, export_gui_bundle, save_gui_design_image,
    )

    design = Design(
        shape=(2, 2), pitch_nm=20000,
        period_nm=np.array([[1000, 1000], [1000, 0]], dtype=np.uint32),
        angle_deg=np.array([[0.0, 45.0], [-30.0, 0.0]], dtype=np.float64),
        active=np.array([[True, True], [True, False]]),
    )

    raw, img = encode_gui_design_image(design, "RGB8 indexed")
    out_img_path = tmp_path / "saved_design.png"
    save_gui_design_image(out_img_path, raw)
    assert out_img_path.exists()
    assert out_img_path.stat().st_size > 50

    bundle_dir = export_gui_bundle(design, tmp_path, layout_name="TEST_BUNDLE")
    assert (bundle_dir / "TEST_BUNDLE.gds").exists()
    assert (bundle_dir / "angles.txt").exists()
    assert (bundle_dir / "gratings.txt").exists()
    assert (bundle_dir / "design.npz").exists()
    assert (bundle_dir / "manifest.json").exists()


def test_design_window_editing_workflow(tmp_path):
    import time
    import tkinter as tk
    from dot_ebl_preview.gui import DesignWindow

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Desktop session unavailable: {error}")
    root.withdraw()
    try:
        win = DesignWindow(root)
        win.path_var.set("test.png")
        win.format_var.set("RGB8 indexed")
        win.pitch_var.set("20")

        win._load()
        start = time.time()
        while win.busy and time.time() - start < 5.0:
            win._poll_results()
            time.sleep(0.05)

        assert win.design is not None
        orig_gratings = [v[0] for v in win._table_data["gratings"]]
        assert 1.0 in orig_gratings

        # Verify columns and channel headings
        assert win.period_table["columns"] == ("value", "channel", "count")
        assert win.angle_table["columns"] == ("value", "channel", "count")
        assert win.period_table.heading("channel")["text"] == "Channel (R)"
        assert win.angle_table.heading("channel")["text"] == "Channel (G)"

        # Verify table items have respective channel values
        p_items = [win.period_table.item(item_id, "values") for item_id in win.period_table.get_children()]
        val_to_chan_p = {row[0]: row[1] for row in p_items}
        assert val_to_chan_p["1"] == "10"
        assert val_to_chan_p["0.9"] == "0"
        assert val_to_chan_p["1.05"] == "15"

        a_items = [win.angle_table.item(item_id, "values") for item_id in win.angle_table.get_children()]
        val_to_chan_a = {row[0]: row[1] for row in a_items}
        assert val_to_chan_a["0"] == "90"
        assert val_to_chan_a["45"] == "135"
        assert val_to_chan_a["-90"] == "0"

        # Change 1.0 to 1.03 (not in test.png)
        win._update_parameter_value("gratings", "1", "1.03")
        mod_gratings = [v[0] for v in win._table_data["gratings"]]
        assert 1.0 not in mod_gratings
        assert 1.03 in mod_gratings

        p_items_mod = [win.period_table.item(item_id, "values") for item_id in win.period_table.get_children()]
        val_to_chan_p_mod = {row[0]: row[1] for row in p_items_mod}
        assert "1.03" in val_to_chan_p_mod
        assert "1" not in val_to_chan_p_mod

        # Check all 4 graph images are present
        assert win.panel_images["source"] is not None
        assert win.panel_images["periods"] is not None
        assert win.panel_images["angles"] is not None

        # Revert
        win._revert_to_original()
        rev_gratings = [v[0] for v in win._table_data["gratings"]]
        assert 1.0 in rev_gratings
        assert 1.03 not in rev_gratings

        p_items_rev = [win.period_table.item(item_id, "values") for item_id in win.period_table.get_children()]
        val_to_chan_p_rev = {row[0]: row[1] for row in p_items_rev}
        assert "1" in val_to_chan_p_rev
        assert val_to_chan_p_rev["1"] == "10"

        win._close()
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def test_parameter_table_entries_rgb8():
    from dot_ebl_preview.gui_logic import parameter_table_entries

    design = Design(
        shape=(2, 2), pitch_nm=20000,
        period_nm=np.array([[900, 1000], [1050, 0]], dtype=np.uint32),
        angle_deg=np.array([[-90.0, 0.0], [45.0, 0.0]], dtype=np.float64),
        active=np.array([[True, True], [True, False]]),
    )
    raw = np.zeros((2, 2, 3), dtype=np.uint8)
    raw[0, 0] = [0, 0, 255]      # 900 nm, -90 deg
    raw[0, 1] = [10, 90, 255]    # 1000 nm, 0 deg
    raw[1, 0] = [15, 135, 255]   # 1050 nm, 45 deg

    chan_p, p_entries = parameter_table_entries(design, "gratings", "RGB8 indexed", raw)
    assert chan_p == "R"
    assert p_entries == [(0.9, "0", 1), (1.0, "10", 1), (1.05, "15", 1)]

    chan_a, a_entries = parameter_table_entries(design, "angles", "RGB8 indexed", raw)
    assert chan_a == "G"
    assert a_entries == [(-90.0, "0", 1), (0.0, "90", 1), (45.0, "135", 1)]

    # Fallback without source_raw
    chan_p2, p_entries2 = parameter_table_entries(design, "gratings", "RGB8 indexed", None)
    assert chan_p2 == "R"
    assert p_entries2 == [(0.9, "0", 1), (1.0, "10", 1), (1.05, "15", 1)]


def test_parameter_table_entries_rgb16():
    from dot_ebl_preview.gui_logic import parameter_table_entries

    design = Design(
        shape=(1, 2), pitch_nm=20000,
        period_nm=np.array([[950, 1100]], dtype=np.uint32),
        angle_deg=np.array([[-72.0, 30.0]], dtype=np.float64),
        active=np.array([[True, True]]),
    )
    raw = np.zeros((1, 2, 3), dtype=np.uint16)
    raw[0, 0] = [950, 25568, 65535]
    raw[0, 1] = [1100, 35768, 65535]

    chan_p, p_entries = parameter_table_entries(design, "gratings", "RGB16 fixed", raw)
    assert chan_p == "R"
    assert p_entries == [(0.95, "950", 1), (1.1, "1100", 1)]

    chan_a, a_entries = parameter_table_entries(design, "angles", "RGB16 fixed", raw)
    assert chan_a == "G"
    assert a_entries == [(-72.0, "25568", 1), (30.0, "35768", 1)]


def test_parameter_table_entries_empty():
    from dot_ebl_preview.gui_logic import parameter_table_entries

    design = Design(
        shape=(2, 2), pitch_nm=20000,
        period_nm=np.zeros((2, 2), dtype=np.uint32),
        angle_deg=np.zeros((2, 2), dtype=np.float64),
        active=np.zeros((2, 2), dtype=bool),
    )
    chan_p, p_entries = parameter_table_entries(design, "gratings", "RGB8 indexed", None)
    assert chan_p == "R"
    assert p_entries == []
