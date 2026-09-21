"""Comprehensive test suite for multi-illumination optical simulation and preview."""

import math
import numpy as np
import pytest
from dataclasses import replace

from dot_ebl_preview.api import LightSource, OpticalSimParams, simulate_cell_optical_color
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.gui_logic import (
    SceneSettings,
    render_scene,
    render_scene_gpu,
)
from dot_ebl_preview.preview.gl_renderer import ReusableGLRenderer
from dot_ebl_preview.preview.realtime import RealtimeViewer


def test_light_source_dataclass_and_validation():
    """Verify LightSource attributes, defaults, and validation checks."""
    l1 = LightSource(pos=(10.0, 20.0, 30.0), source_radius_factor=15.0, intensity=1.5)
    assert l1.pos == (10.0, 20.0, 30.0)
    assert l1.source_radius_factor == 15.0
    assert l1.intensity == 1.5
    assert l1.source_size_mm == 15.0
    l1.validated()

    # Invalid positions
    with pytest.raises(ValueError, match="3-tuple"):
        LightSource(pos=(1.0, 2.0)).validated()

    # Negative radius
    with pytest.raises(ValueError, match="physical size"):
        LightSource(pos=(0.0, 0.0, 10.0), source_radius_factor=-1.0).validated()


    # Negative intensity
    with pytest.raises(ValueError, match="intensity"):
        LightSource(pos=(0.0, 0.0, 10.0), intensity=-0.5).validated()


def test_optical_sim_params_multi_light():
    """Verify OpticalSimParams handles lights tuple and syncs with legacy light_pos."""
    l1 = LightSource(pos=(0.0, 20.0, 30.0), source_radius_factor=20.0, intensity=1.0)
    l2 = LightSource(pos=(10.0, -15.0, 40.0), source_radius_factor=10.0, intensity=0.5)

    params = OpticalSimParams(lights=(l1, l2))
    assert len(params.lights) == 2
    assert params.get_lights() == (l1, l2)
    # Primary light syncs to legacy attributes
    assert params.light_pos == (0.0, 20.0, 30.0)
    assert params.source_radius_factor == 20.0

    # Test single-light legacy initialization
    legacy_params = OpticalSimParams(light_pos=(5.0, 15.0, 25.0), source_radius_factor=12.0)
    lights = legacy_params.get_lights()
    assert len(lights) == 1
    assert lights[0].pos == (5.0, 15.0, 25.0)
    assert lights[0].source_radius_factor == 12.0
    assert lights[0].intensity == 1.0

    # Validation: empty lights
    with pytest.raises(ValueError, match="at least one light"):
        OpticalSimParams(lights=()).validated()

    # Validation: more than 8 lights
    too_many = tuple(LightSource(pos=(0.0, 0.0, 10.0)) for _ in range(9))
    with pytest.raises(ValueError, match="Maximum 8"):
        OpticalSimParams(lights=too_many).validated()


def test_additive_superposition_radiance_doubling():
    """Verify that two identical lights produce exact 2x unclipped radiance."""
    # Turn off gamut mapping to test raw linear XYZ -> sRGB transfer
    l1 = LightSource(pos=(0.0, 20.6487533, 29.4891314), source_radius_factor=0.0, intensity=1.0)
    params_single = OpticalSimParams(lights=(l1,), apply_gamut_mapping=False)
    single_color = np.asarray(simulate_cell_optical_color(1000, 0.0, params=params_single))

    params_double = OpticalSimParams(lights=(l1, l1), apply_gamut_mapping=False)
    double_color = np.asarray(simulate_cell_optical_color(1000, 0.0, params=params_double))

    assert single_color.sum() > 0.0
    np.testing.assert_allclose(double_color, single_color * 2.0, rtol=1e-5)


def test_intensity_linear_scaling():
    """Verify that light source intensity scales linear radiance proportionally."""
    l_full = LightSource(pos=(0.0, 20.6487533, 29.4891314), intensity=1.0)
    l_half = LightSource(pos=(0.0, 20.6487533, 29.4891314), intensity=0.5)
    l_zero = LightSource(pos=(0.0, 20.6487533, 29.4891314), intensity=0.0)

    c_full = np.asarray(simulate_cell_optical_color(1000, 0.0, params=OpticalSimParams(lights=(l_full,), apply_gamut_mapping=False)))
    c_half = np.asarray(simulate_cell_optical_color(1000, 0.0, params=OpticalSimParams(lights=(l_half,), apply_gamut_mapping=False)))
    c_zero = np.asarray(simulate_cell_optical_color(1000, 0.0, params=OpticalSimParams(lights=(l_zero,), apply_gamut_mapping=False)))

    np.testing.assert_allclose(c_half, c_full * 0.5, rtol=1e-5)
    np.testing.assert_allclose(c_zero, np.zeros(3), atol=1e-10)


def test_multi_light_color_mixing():
    """Verify additive color mixing from two differently oriented light sources."""
    # Light 1: on-axis in +Y produces yellow-green for 1000nm grating at 0 deg
    l1 = LightSource(pos=(0.0, 20.6487533, 29.4891314), intensity=1.0)
    # Light 2: cross-axis in +X does not diffract for 0 deg grating, but diffracts for 90 deg grating
    l2 = LightSource(pos=(20.6487533, 0.0, 29.4891314), intensity=1.0)

    # For grating at 0 deg:
    c_l1 = np.asarray(simulate_cell_optical_color(1000, 0.0, params=OpticalSimParams(lights=(l1,), apply_gamut_mapping=False)))
    c_l2 = np.asarray(simulate_cell_optical_color(1000, 0.0, params=OpticalSimParams(lights=(l2,), apply_gamut_mapping=False)))
    c_both = np.asarray(simulate_cell_optical_color(1000, 0.0, params=OpticalSimParams(lights=(l1, l2), apply_gamut_mapping=False)))

    # l1 contributes, l2 is cross-axis so negligible
    assert c_l1.sum() > 1e-4
    assert np.max(c_l2) < 1e-5
    np.testing.assert_allclose(c_both, c_l1 + c_l2, rtol=1e-5)


    # Now for 45 deg grating, both lights contribute symmetrically:
    c45_l1 = np.asarray(simulate_cell_optical_color(1000, 45.0, params=OpticalSimParams(lights=(l1,), apply_gamut_mapping=False)))
    c45_l2 = np.asarray(simulate_cell_optical_color(1000, 45.0, params=OpticalSimParams(lights=(l2,), apply_gamut_mapping=False)))
    c45_both = np.asarray(simulate_cell_optical_color(1000, 45.0, params=OpticalSimParams(lights=(l1, l2), apply_gamut_mapping=False)))

    assert c45_l1.sum() > 1e-4
    assert c45_l2.sum() > 1e-4

    # Check symmetry between rotated lights
    np.testing.assert_allclose(c45_l1, c45_l2, rtol=1e-3)
    # Check exact additive sum
    np.testing.assert_allclose(c45_both, c45_l1 + c45_l2, rtol=1e-5)


def test_opengl_multi_light_matches_cpu():
    """Verify GPU GLSL multi-light shader matches CPU spectral reference within 4 integer RGB levels."""
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")

    shape = (6, 6)
    periods = np.tile(np.array([900, 950, 1000, 1050, 1100, 1150], dtype=np.uint32), (6, 1))
    angles = np.zeros(shape, dtype=np.float64)
    angles[:, 1] = 15.0
    angles[:, 2] = 45.0
    angles[:, 3] = -30.0
    active = np.ones(shape, dtype=bool)
    active[0, 0] = False
    fallback = np.zeros(shape, dtype=np.float32)
    fallback[0, 0] = 0.2
    design = Design(shape=shape, pitch_nm=20000, period_nm=periods,
                    angle_deg=angles, active=active, fallback_intensity=fallback)

    # 3 distinct lights with different positions, sizes, intensities
    l1 = LightSource(pos=(0.0, 20.6487533, 29.4891314), source_radius_factor=10.0, intensity=1.0)
    l2 = LightSource(pos=(15.0, -10.0, 35.0), source_radius_factor=5.0, intensity=0.7)
    l3 = LightSource(pos=(-20.0, 10.0, 40.0), source_radius_factor=20.0, intensity=0.5)

    scene = SceneSettings(
        lights=(l1, l2, l3),
        camera_pos=(0.3, 0.0, 66.0),
        orientation_deg=5.0,
        aperture_mm=4.0,
    )

    try:
        gpu = np.asarray(render_scene_gpu(design, scene), dtype=np.int16)
    except RuntimeError as error:
        if "unavailable" in str(error) or "could not initialize" in str(error):
            pytest.skip(str(error))
        raise
    cpu = np.asarray(render_scene(design, scene), dtype=np.int16)

    assert gpu.shape == cpu.shape == (6, 6, 3)
    assert int(cpu.max()) > 20
    # Strict CPU vs GPU parity
    diff = np.abs(gpu - cpu)
    max_diff = int(np.max(diff))
    assert max_diff <= 4, f"Max difference was {max_diff} at {np.unravel_index(np.argmax(diff), diff.shape)}"
    # Fallback cell parity
    assert gpu[0, 0].tolist() == [51, 51, 51]


def test_scene_settings_multi_light_sync_and_validation():
    """Verify SceneSettings multi-light handling and backward compatibility."""
    l1 = LightSource(pos=(1.0, 2.0, 3.0), source_radius_factor=5.0, intensity=1.0)
    l2 = LightSource(pos=(4.0, 5.0, 6.0), source_radius_factor=10.0, intensity=0.8)

    scene = SceneSettings(lights=(l1, l2))
    assert len(scene.lights) == 2
    assert scene.light_pos == (1.0, 2.0, 3.0)
    assert scene.source_size_mm == 5.0
    scene.validated()

    # Empty lights raises ValueError
    with pytest.raises(ValueError, match="at least one"):
        SceneSettings(lights=()).validated()

    # > 8 lights raises ValueError
    nine_lights = tuple(LightSource(pos=(0.0, 0.0, 10.0)) for _ in range(9))
    with pytest.raises(ValueError, match="Maximum 8"):
        SceneSettings(lights=nine_lights).validated()


def test_realtime_viewer_active_light_orbit():
    """Verify RealtimeViewer orbits only the active light source when multiple lights are present."""
    pytest.importorskip("glfw")
    pytest.importorskip("OpenGL")

    shape = (2, 2)
    design = Design(
        shape=shape, pitch_nm=20000,
        period_nm=np.full(shape, 1000, dtype=np.uint32),
        angle_deg=np.zeros(shape), active=np.ones(shape, dtype=bool),
    )

    l1 = LightSource(pos=(0.0, 20.0, 30.0), intensity=1.0)
    l2 = LightSource(pos=(10.0, 0.0, 30.0), intensity=0.8)

    scene = SceneSettings(lights=(l1, l2), camera_pos=(0.0, 0.0, 66.0))
    viewer = RealtimeViewer(design, scene, visible=False)
    viewer.start()

    try:
        assert viewer.active_light_index == 0
        assert len(viewer.scene.lights) == 2

        # Orbit active light (index 0)
        pos0_before = viewer.scene.lights[0].pos
        pos1_before = viewer.scene.lights[1].pos
        viewer.orbit("light", delta_az=30.0, delta_el=10.0)

        # Light 0 should change, Light 1 should remain unchanged
        assert viewer.scene.lights[0].pos != pos0_before
        assert viewer.scene.lights[1].pos == pos1_before

        # Switch active light to index 1
        viewer.active_light_index = 1
        pos0_current = viewer.scene.lights[0].pos
        viewer.orbit("light", delta_az=-20.0, delta_el=5.0)

        # Light 0 remains unchanged, Light 1 changes
        assert viewer.scene.lights[0].pos == pos0_current
        assert viewer.scene.lights[1].pos != pos1_before
    finally:
        viewer.close()


def test_cli_preview_with_multiple_lights(tmp_path):
    """Verify CLI preview command with multiple --light flags."""
    from dot_ebl_preview.cli import main

    shape = (4, 4)
    design = Design(
        shape=shape, pitch_nm=20000,
        period_nm=np.full(shape, 1000, dtype=np.uint32),
        angle_deg=np.zeros(shape), active=np.ones(shape, dtype=bool),
    )
    npz_path = tmp_path / "test_design.npz"
    from dot_ebl_preview.io.artifacts import save_design_artifact
    save_design_artifact(npz_path, design)

    out_png = tmp_path / "multi_preview.png"
    code = main([
        "preview",
        str(npz_path),
        "-o", str(out_png),
        "--light", "0", "20.65", "29.49", "10", "1.0",
        "--light", "15", "-10", "35", "5", "0.7",
    ])
    assert code == 0
    assert out_png.exists()
    assert out_png.stat().st_size > 50


def test_gui_multi_source_management():
    """Verify GUI source addition, switching, editing, and removal."""
    import tkinter as tk
    from dot_ebl_preview.gui import DesignWindow

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Desktop session unavailable: {error}")
    root.withdraw()

    try:
        win = DesignWindow(root)
        assert len(win.sources_data) == 1
        assert win.active_source_idx == 0

        # Add a 2nd light source
        win._add_source()
        assert len(win.sources_data) == 2
        assert win.active_source_idx == 1
        assert win.source_selector_var.get() == "Source 2"

        # Edit 2nd source pos and intensity
        win.source_vars["x"].set("15.0")
        win.source_vars["intensity"].set("0.6")
        win._sync_current_source_to_data()
        assert win.sources_data[1]["x"] == "15.0"
        assert win.sources_data[1]["intensity"] == "0.6"

        # Switch back to Source 1
        win.source_selector_var.set("Source 1")

        win._source_selection_changed()
        assert win.active_source_idx == 0
        assert float(win.source_vars["intensity"].get()) == pytest.approx(1.0)


        # Verify SceneSettings derives 2 lights
        scene = win._scene_settings(report_error=True)
        assert scene is not None
        assert len(scene.lights) == 2
        assert scene.lights[1].pos[0] == pytest.approx(15.0)
        assert scene.lights[1].intensity == pytest.approx(0.6)

        # Remove Source 1 (now only Source 2 remains)
        win._remove_source()
        assert len(win.sources_data) == 1
        assert win.active_source_idx == 0
        assert win.sources_data[0]["x"] == "15.0"
        assert win.sources_data[0]["intensity"] == "0.6"
        # Removing when only 1 source remains is blocked
        assert win.remove_source_btn.instate(["disabled"])
    finally:
        try:
            root.destroy()
        except Exception:
            pass


