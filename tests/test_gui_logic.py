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
