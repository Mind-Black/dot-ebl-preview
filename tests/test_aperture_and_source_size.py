"""Tests for observer aperture and light source physical size controls."""

import math
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.gui_logic import SceneSettings, render_scene, render_scene_gpu
from dot_ebl_preview.optics.engine import OpticalSimParams, simulate_cell_optical_color
from dot_ebl_preview.preview.gl_renderer import render_opengl_preview


def test_default_parameters_match_original_behavior():
    params = OpticalSimParams()
    assert params.aperture_radius_factor == 5.0
    assert params.source_radius_factor == 0.0
    assert params.aperture_mm == 5.0
    assert params.source_size_mm == 0.0

    color = simulate_cell_optical_color(1000, 0.0, params=params)
    assert color[1] > 0.5  # Yellow-green green component


def test_observer_aperture_effects():
    # Zero aperture collects no light
    zero_aperture = simulate_cell_optical_color(
        1000, 0.0, params=OpticalSimParams(aperture_radius_factor=0.0)
    )
    assert zero_aperture == (0.0, 0.0, 0.0)

    # Smaller aperture collects less light and has narrower acceptance
    small_aperture = np.asarray(simulate_cell_optical_color(
        1000, 0.0, params=OpticalSimParams(aperture_radius_factor=1.0)
    ))
    standard_aperture = np.asarray(simulate_cell_optical_color(
        1000, 0.0, params=OpticalSimParams(aperture_radius_factor=5.0)
    ))
    large_aperture = np.asarray(simulate_cell_optical_color(
        1000, 0.0, params=OpticalSimParams(aperture_radius_factor=12.0)
    ))

    assert small_aperture.sum() > 0.0
    assert standard_aperture.sum() > small_aperture.sum()
    assert large_aperture.sum() >= standard_aperture.sum()


def test_light_source_physical_size_broadening():
    # In the wing (e.g. 10 mm off-axis at 66 mm distance), a point source is extinguished
    wing_cam = (10.0, 0.0, 66.0)
    pt_wing = np.asarray(simulate_cell_optical_color(
        1000, 0.0,
        params=OpticalSimParams(camera_pos=wing_cam, source_radius_factor=0.0)
    ))
    ext_wing = np.asarray(simulate_cell_optical_color(
        1000, 0.0,
        params=OpticalSimParams(camera_pos=wing_cam, source_radius_factor=8.0)
    ))

    # Extended source maintains broad illumination in the wings where point source is dark
    assert pt_wing.sum() < 0.01
    assert ext_wing.sum() > 0.10

    # On-axis, extended source mixes wavelengths together (higher spectral mixing in minority channels)
    on_axis_cam = (0.0, 0.0, 66.0)
    pt_center = np.asarray(simulate_cell_optical_color(
        1000, 0.0,
        params=OpticalSimParams(camera_pos=on_axis_cam, source_radius_factor=0.0)
    ))
    ext_center = np.asarray(simulate_cell_optical_color(
        1000, 0.0,
        params=OpticalSimParams(camera_pos=on_axis_cam, source_radius_factor=8.0)
    ))
    # Point source has virtually zero blue at this angle (< 0.01); extended source mixes blue (> 0.05)
    assert pt_center[2] < 0.01
    assert ext_center[2] > 0.05


def test_scene_settings_validation():
    # Valid defaults
    s = SceneSettings()
    assert s.aperture_mm == 5.0
    assert s.source_size_mm == 0.0
    assert s.validated() is s

    # Valid custom values
    s_custom = SceneSettings(aperture_mm=2.5, source_size_mm=4.0)
    assert s_custom.validated().aperture_mm == 2.5
    assert s_custom.validated().source_size_mm == 4.0

    # Negative aperture
    with pytest.raises(ValueError, match="Observer aperture must be non-negative"):
        SceneSettings(aperture_mm=-1.0).validated()

    # Negative source size
    with pytest.raises(ValueError, match="Light source physical size must be non-negative"):
        SceneSettings(source_size_mm=-0.5).validated()

    # Non-finite values
    with pytest.raises(ValueError, match="must be finite numbers"):
        SceneSettings(aperture_mm=float("nan")).validated()


def test_cpu_and_gpu_consistency_with_aperture_and_source_size():
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")

    shape = (4, 4)
    periods = np.full(shape, 1000, dtype=np.uint32)
    angles = np.zeros(shape, dtype=np.float64)
    active = np.ones(shape, dtype=bool)
    design = Design(shape=shape, pitch_nm=20000, period_nm=periods,
                    angle_deg=angles, active=active)

    # Test with custom aperture and non-zero extended light source
    scene = SceneSettings(
        light_pos=(0.0, 20.6487533, 29.4891314),
        camera_pos=(0.0, 0.0, 66.0),
        orientation_deg=0.0,
        aperture_mm=3.5,
        source_size_mm=2.0,
    )

    try:
        gpu = np.asarray(render_scene_gpu(design, scene), dtype=np.int16)
    except RuntimeError as error:
        if "unavailable" in str(error) or "could not initialize" in str(error):
            pytest.skip(str(error))
        raise

    cpu = np.asarray(render_scene(design, scene), dtype=np.int16)

    assert gpu.shape == cpu.shape == (4, 4, 3)
    assert int(cpu.max()) > 10
    # Difference should be within rendering tolerance
    assert np.max(np.abs(gpu - cpu)) <= 5


def test_cli_preview_with_aperture_and_light_size(tmp_path: Path):
    from dot_ebl_preview.cli import main

    out_file = tmp_path / "test_preview.png"
    ret = main([
        "preview",
        "_INPUT/test.png",
        "-o", str(out_file),
        "--aperture-mm", "8.0",
        "--light-size-mm", "3.0",
    ])
    assert ret == 0
    assert out_file.exists()
    img = Image.open(out_file)
    assert img.size == (128, 128)
    arr = np.asarray(img)
    assert arr.sum() > 0


def test_gui_aperture_and_source_size_variables():
    import tkinter as tk
    from dot_ebl_preview.gui import DesignWindow

    try:
        root = tk.Tk()
    except tk.TclError as err:
        pytest.skip(f"No display: {err}")
    root.withdraw()
    window = None
    try:
        window = DesignWindow(root)
        assert "aperture" in window.observer_vars
        assert "size" in window.source_vars
        assert window.observer_vars["aperture"].get() == "5.0"
        assert window.source_vars["size"].get() == "0.0"

        # Check _scene_settings produces matching SceneSettings
        scene = window._scene_settings(report_error=False)
        assert scene is not None
        assert scene.aperture_mm == 5.0
        assert scene.source_size_mm == 0.0

        # Change variables
        window.observer_vars["aperture"].set("8.5")
        window.source_vars["size"].set("3.2")
        updated = window._scene_settings(report_error=False)
        assert updated is not None
        assert updated.aperture_mm == 8.5
        assert updated.source_size_mm == 3.2

        # Check _apply_viewer_scene
        new_scene = SceneSettings(aperture_mm=12.0, source_size_mm=4.5)
        window._apply_viewer_scene(new_scene)
        assert float(window.observer_vars["aperture"].get()) == 12.0
        assert float(window.source_vars["size"].get()) == 4.5
    finally:
        if window is not None:
            window._close()
        else:
            root.destroy()
