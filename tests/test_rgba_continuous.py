"""Unit and integration tests for rgba-continuous-v1 profile and masked bilateral filter."""

import numpy as np
import pytest
from pathlib import Path

from dot_ebl_preview.api import build_design, inspect_design
from dot_ebl_preview.cli import main as cli_main
from dot_ebl_preview.core.encoding import RGBAContinuousProfile
from dot_ebl_preview.core.filters import apply_masked_bilateral_filter
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.gui_logic import (
    encode_gui_design_image,
    load_gui_design,
    parameter_table_entries,
    save_gui_design_image,
)
from dot_ebl_preview.io.images import load_image_raw, load_image_rgb, save_image_rgba


def test_rgba_profile_validation():
    """Verify profile parameter validations."""
    with pytest.raises(ValueError, match="min_period_nm must be positive"):
        RGBAContinuousProfile(min_period_nm=0)

    with pytest.raises(ValueError, match="greater than min_period_nm"):
        RGBAContinuousProfile(min_period_nm=1000, max_period_nm=900)

    with pytest.raises(ValueError, match="greater than min_angle_deg"):
        RGBAContinuousProfile(min_angle_deg=45, max_angle_deg=-45)

    with pytest.raises(ValueError, match="filter_diameter must be >= 1"):
        RGBAContinuousProfile(filter_diameter=0)


def test_rgba_profile_to_from_dict():
    """Verify serialization roundtrip."""
    prof = RGBAContinuousProfile(
        min_period_nm=500.0,
        max_period_nm=1400.0,
        min_angle_deg=-60.0,
        max_angle_deg=60.0,
        apply_filter=False,
        round_integer_angles=True,
        round_period_50nm=True,
    )
    d = prof.to_dict()
    assert d["round_integer_angles"] is True
    assert d["round_period_50nm"] is True
    restored = RGBAContinuousProfile.from_dict(d)
    assert restored.min_period_nm == 500.0
    assert restored.max_period_nm == 1400.0
    assert restored.min_angle_deg == -60.0
    assert restored.max_angle_deg == 60.0
    assert restored.apply_filter is False
    assert restored.round_integer_angles is True
    assert restored.round_period_50nm is True


def test_rgba_8bit_decode_linear_mapping():
    """Verify 8-bit RGBA decoding linear mapping, B channel ignoring, and A thresholding."""
    # 3x1 image:
    # Pixel 0: R=0 (min period 400), G=0 (min angle -90), B=200 (ignored), A=255 (active)
    # Pixel 1: R=255 (max period 1600), G=255 (max angle 90), B=0, A=128 (active threshold)
    # Pixel 2: R=128, G=128, B=50, A=127 (inactive threshold: < 128)
    arr = np.array([
        [[0, 0, 200, 255], [255, 255, 0, 128], [128, 128, 50, 127]]
    ], dtype=np.uint8)

    prof = RGBAContinuousProfile(apply_filter=False)
    design = prof.decode(arr, pitch_nm=20000)

    assert design.shape == (1, 3)
    assert design.active[0, 0] is np.True_ or design.active[0, 0] == True
    assert design.active[0, 1] is np.True_ or design.active[0, 1] == True
    assert design.active[0, 2] is np.False_ or design.active[0, 2] == False

    # Pixel 0: 400 nm, -90.0 deg
    assert design.period_nm[0, 0] == 400
    assert abs(design.angle_deg[0, 0] - (-90.0)) < 1e-6

    # Pixel 1: 1600 nm, +90.0 deg
    assert design.period_nm[0, 1] == 1600
    assert abs(design.angle_deg[0, 1] - 90.0) < 1e-6

    # Pixel 2: inactive outputs period=0, angle=0
    assert design.period_nm[0, 2] == 0
    assert design.angle_deg[0, 2] == 0.0


def test_rgba_16bit_decode_linear_mapping():
    """Verify 16-bit RGBA decoding linear mapping and A thresholding at 32768."""
    arr = np.array([
        [[0, 0, 0, 65535], [65535, 65535, 0, 32768], [32768, 32768, 0, 32767]]
    ], dtype=np.uint16)

    prof = RGBAContinuousProfile(apply_filter=False)
    design = prof.decode(arr, pitch_nm=20000)

    assert design.active[0, 0] == True
    assert design.active[0, 1] == True
    assert design.active[0, 2] == False

    assert design.period_nm[0, 0] == 400
    assert abs(design.angle_deg[0, 0] - (-90.0)) < 1e-6

    assert design.period_nm[0, 1] == 1600
    assert abs(design.angle_deg[0, 1] - 90.0) < 1e-6

    assert design.period_nm[0, 2] == 0
    assert design.angle_deg[0, 2] == 0.0


def test_rgba_encode_roundtrip():
    """Verify encoding design to RGBA uint8 and uint16."""
    shape = (2, 2)
    period_nm = np.array([[500, 1200], [0, 800]], dtype=np.uint32)
    angle_deg = np.array([[-30.0, 45.0], [0.0, 0.0]], dtype=np.float64)
    active = np.array([[True, True], [False, True]], dtype=np.bool_)

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
    prof = RGBAContinuousProfile(apply_filter=False)

    # 8-bit encode
    img8, report8 = prof.encode(design, bit_depth=8)
    assert img8.dtype == np.uint8
    assert img8.shape == (2, 2, 4)
    assert report8.active_count == 3
    assert report8.max_period_error_nm < 5.0  # 8-bit period step is ~4.7 nm

    # Active pixels have A=255, inactive A=0, B=0
    assert img8[0, 0, 3] == 255
    assert img8[1, 0, 3] == 0
    assert np.all(img8[:, :, 2] == 0)

    # 16-bit encode
    img16, report16 = prof.encode(design, bit_depth=16)
    assert img16.dtype == np.uint16
    assert report16.max_period_error_nm < 0.1
    assert report16.max_angle_error_deg < 0.01
    assert img16[0, 0, 3] == 65535
    assert img16[1, 0, 3] == 0


def test_masked_bilateral_filter_valid_only():
    """Verify inactive cells are strictly masked out and never bleed into active cells."""
    shape = (3, 3)
    period_nm = np.zeros(shape, dtype=np.uint32)
    angle_deg = np.zeros(shape, dtype=np.float64)
    active = np.zeros(shape, dtype=np.bool_)

    # Center is active with period 1000 nm, angle 30 deg
    active[1, 1] = True
    period_nm[1, 1] = 1000
    angle_deg[1, 1] = 30.0

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
    filtered = apply_masked_bilateral_filter(design, diameter=3)

    assert filtered.period_nm[1, 1] == 1000
    assert abs(filtered.angle_deg[1, 1] - 30.0) < 1e-6

    # Inactive neighbors must remain 0
    assert np.all(filtered.period_nm[~active] == 0)
    assert np.all(filtered.angle_deg[~active] == 0.0)


def test_masked_bilateral_filter_axial_angle_symmetry():
    """Verify axial angle smoothing handles 180-deg diffraction symmetry across boundaries."""
    shape = (1, 5)
    period_nm = np.full(shape, 1000, dtype=np.uint32)
    # Transition across ±90 deg: -88, -89, -90, -91, -92
    angle_deg = np.array([[-88.0, -89.0, -90.0, -91.0, -92.0]], dtype=np.float64)
    active = np.ones(shape, dtype=np.bool_)

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
    filtered = apply_masked_bilateral_filter(design, diameter=3)

    # Middle angle should stay near -90 degrees, not flip to +90 degrees
    assert -95.0 <= filtered.angle_deg[0, 2] <= -85.0


def test_png_8bit_and_16bit_rgba_roundtrip(tmp_path: Path):
    """Verify PNG saving and loading for 8-bit and 16-bit RGBA files."""
    rng = np.random.default_rng(123)

    # 8-bit RGBA
    arr8 = rng.integers(0, 256, size=(6, 8, 4), dtype=np.uint8)
    p8 = tmp_path / "test8_rgba.png"
    save_image_rgba(p8, arr8)
    loaded8_raw = load_image_raw(p8)
    assert loaded8_raw.shape == (6, 8, 4)
    assert loaded8_raw.dtype == np.uint8
    assert np.array_equal(loaded8_raw, arr8)

    # Backward compatibility: load_image_rgb drops alpha
    loaded8_rgb = load_image_rgb(p8)
    assert loaded8_rgb.shape == (6, 8, 3)
    assert np.array_equal(loaded8_rgb, arr8[:, :, :3])

    # 16-bit RGBA
    arr16 = rng.integers(0, 65536, size=(6, 8, 4), dtype=np.uint16)
    p16 = tmp_path / "test16_rgba.png"
    save_image_rgba(p16, arr16)
    loaded16_raw = load_image_raw(p16)
    assert loaded16_raw.shape == (6, 8, 4)
    assert loaded16_raw.dtype == np.uint16
    assert np.array_equal(loaded16_raw, arr16)


def test_build_design_with_rgba_continuous(tmp_path: Path):
    """Verify build_design API works with rgba-continuous-v1 profile."""
    # Create simple RGBA test PNG
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    arr[:, :, 0] = 128  # Period: 400 + 128/255*1200 ~ 1002 nm
    arr[:, :, 1] = 64   # Angle: -90 + 64/255*180 ~ -44.8 deg
    arr[:, :, 3] = 255  # Active
    img_path = tmp_path / "test_rgba.png"
    save_image_rgba(img_path, arr)

    design = build_design(
        img_path,
        encoding_profile="rgba-continuous-v1",
        pitch_nm=25000,
        apply_filter=True,
    )
    assert design.shape == (4, 4)
    assert design.pitch_nm == 25000
    assert design.active_count == 16
    assert 990 <= design.period_nm[0, 0] <= 1015
    assert -48.0 <= design.angle_deg[0, 0] <= -42.0

    info = inspect_design(design)
    assert info["active_cells"] == 16
    assert info["total_cells"] == 16


def test_cli_inspect_and_export_rgba(tmp_path: Path):
    """Verify CLI inspect and export with rgba-continuous-v1 and --filter / --no-filter."""
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    arr[:, :, 0] = 200
    arr[:, :, 1] = 100
    arr[:, :, 3] = 255
    img_path = tmp_path / "cli_rgba.png"
    save_image_rgba(img_path, arr)

    # Inspect
    ret = cli_main(["inspect", str(img_path), "--profile", "rgba-continuous-v1"])
    assert ret == 0

    # Export with --no-filter
    out_dir = tmp_path / "_OUT"
    ret = cli_main([
        "export", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--no-filter",
        "-o", str(out_dir),
        "--name", "RGBA_HOLO",
    ])
    assert ret == 0
    bundle_dirs = list(out_dir.glob("*RGBA_HOLO"))
    assert len(bundle_dirs) == 1
    assert (bundle_dirs[0] / "RGBA_HOLO.gds").exists()
    assert (bundle_dirs[0] / "manifest.json").exists()


def test_gui_logic_rgba_continuous(tmp_path: Path):
    """Verify gui_logic operations with RGBA continuous format."""
    arr = np.zeros((4, 4, 4), dtype=np.uint8)
    arr[:, :, 0] = 150
    arr[:, :, 1] = 80
    arr[:, :, 3] = 255
    img_path = tmp_path / "gui_rgba.png"
    save_image_rgba(img_path, arr)

    design = load_gui_design(
        img_path,
        image_format="RGBA continuous",
        pitch_um=20.0,
        min_period_nm=400.0,
        max_period_nm=1600.0,
        min_angle_deg=-90.0,
        max_angle_deg=90.0,
        apply_filter=True,
    )
    assert design.active_count == 16

    chan_p, p_entries = parameter_table_entries(design, "gratings", "RGBA continuous", arr)
    chan_a, a_entries = parameter_table_entries(design, "angles", "RGBA continuous", arr)
    assert chan_p == "R"
    assert chan_a == "G"
    assert len(p_entries) > 0
    assert len(a_entries) > 0

    raw_arr, pil_img = encode_gui_design_image(design, "RGBA continuous")
    assert raw_arr.shape == (4, 4, 4)
    assert pil_img.mode == "RGBA"

    saved_path = save_gui_design_image(tmp_path / "gui_saved.png", raw_arr)
    assert saved_path.exists()


def test_rgba_all_inactive_image(tmp_path: Path):
    """Verify all-inactive RGBA image decodes and encodes cleanly without errors."""
    arr = np.zeros((4, 4, 4), dtype=np.uint8)  # A=0 everywhere
    arr[:, :, 0] = 255
    arr[:, :, 1] = 255
    img_path = tmp_path / "all_inactive.png"
    save_image_rgba(img_path, arr)

    prof = RGBAContinuousProfile(apply_filter=True)
    design = prof.decode(arr, pitch_nm=20000)
    assert design.active_count == 0
    assert np.all(design.period_nm == 0)
    assert np.all(design.angle_deg == 0.0)

    encoded, report = prof.encode(design, bit_depth=8)
    assert report.active_count == 0
    assert encoded.shape == (4, 4, 4)
    assert np.all(encoded[:, :, 3] == 0)


def test_rgba_16bit_build_design_and_gui(tmp_path: Path):
    """Verify 16-bit RGBA PNG through build_design and load_gui_design."""
    arr16 = np.zeros((4, 4, 4), dtype=np.uint16)
    # R: half-scale = 32768 -> 400 + 0.5 * 1200 = 1000 nm
    arr16[:, :, 0] = 32768
    # G: half-scale = 32768 -> -90 + 0.5 * 180 = 0.0 deg
    arr16[:, :, 1] = 32768
    # A: 65535 (active)
    arr16[:, :, 3] = 65535

    img_path = tmp_path / "test16_build.png"
    save_image_rgba(img_path, arr16)

    design = build_design(img_path, encoding_profile="rgba-continuous-v1", pitch_nm=20000)
    assert design.active_count == 16
    assert 999 <= design.period_nm[0, 0] <= 1001
    assert abs(design.angle_deg[0, 0]) < 0.1

    gui_design = load_gui_design(
        img_path,
        image_format="RGBA continuous",
        pitch_um=20.0,
        min_period_nm=500.0,
        max_period_nm=1500.0,
        min_angle_deg=-45.0,
        max_angle_deg=45.0,
        apply_filter=False,
    )
    # Half-scale on 500..1500 is 1000 nm, and on -45..+45 is 0.0 deg
    assert 999 <= gui_design.period_nm[0, 0] <= 1001
    assert abs(gui_design.angle_deg[0, 0]) < 0.1


def test_masked_filter_no_bleeding_at_boundary():
    """Verify active cells at boundaries do not get pulled down by inactive background zeros."""
    shape = (5, 5)
    period_nm = np.zeros(shape, dtype=np.uint32)
    angle_deg = np.zeros(shape, dtype=np.float64)
    active = np.zeros(shape, dtype=np.bool_)

    # Left two columns active with period 1400 nm and angle 45 deg
    active[:, :2] = True
    period_nm[:, :2] = 1400
    angle_deg[:, :2] = 45.0

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
    filtered = apply_masked_bilateral_filter(design, diameter=3)

    # Active boundary column (col 1) must remain 1400 nm, NOT bleed toward 0
    assert np.all(filtered.period_nm[:, :2] == 1400)
    assert np.allclose(filtered.angle_deg[:, :2], 45.0)

    # Inactive columns must remain 0
    assert np.all(filtered.period_nm[:, 2:] == 0)
    assert np.allclose(filtered.angle_deg[:, 2:], 0.0)


def test_cli_custom_bounds_inspect(tmp_path: Path):
    """Verify CLI inspect handles custom bounds."""
    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 255  # Max
    arr[:, :, 1] = 0    # Min
    arr[:, :, 3] = 255  # Active
    img_path = tmp_path / "cli_bounds.png"
    save_image_rgba(img_path, arr)

    ret = cli_main([
        "inspect", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--min-period-nm", "500",
        "--max-period-nm", "1500",
        "--min-angle-deg", "-45",
        "--max-angle-deg", "45",
    ])
    assert ret == 0


def test_rgba_round_integer_angles_without_filter():
    """Verify active angles are rounded to integer degrees when round_integer_angles is True."""
    # 3x1 image:
    # Pixel 0: G=64 -> -90 + 64/255 * 180 = -44.8235... deg -> rounded to -45.0
    # Pixel 1: G=191 -> -90 + 191/255 * 180 = 44.8235... deg -> rounded to 45.0
    # Pixel 2: Inactive (A=0) -> remains 0.0
    arr = np.array([
        [[128, 64, 0, 255], [128, 191, 0, 255], [128, 64, 0, 0]]
    ], dtype=np.uint8)

    # Without rounding
    prof_raw = RGBAContinuousProfile(apply_filter=False, round_integer_angles=False)
    design_raw = prof_raw.decode(arr)
    assert not np.isclose(design_raw.angle_deg[0, 0], -45.0, atol=1e-3)
    assert abs(design_raw.angle_deg[0, 0] - (-44.8235)) < 0.01

    # With rounding
    prof_rounded = RGBAContinuousProfile(apply_filter=False, round_integer_angles=True)
    design_rounded = prof_rounded.decode(arr)
    assert design_rounded.angle_deg[0, 0] == -45.0
    assert design_rounded.angle_deg[0, 1] == 45.0
    # Inactive cell remains 0.0
    assert design_rounded.angle_deg[0, 2] == 0.0


def test_rgba_round_integer_angles_with_filter():
    """Verify rounding occurs after bilateral filtering so final angles are exact integers."""
    # Gradient across pixels that after bilateral filter would have continuous non-integer values
    arr = np.array([
        [[128, 50, 0, 255], [128, 70, 0, 255], [128, 90, 0, 255]]
    ], dtype=np.uint8)

    prof = RGBAContinuousProfile(apply_filter=True, round_integer_angles=True)
    design = prof.decode(arr)

    for c in range(3):
        angle = design.angle_deg[0, c]
        assert angle == round(angle), f"Angle {angle} is not an exact integer"


def test_build_design_round_integer_angles(tmp_path: Path):
    """Verify build_design respects round_integer_angles parameter."""
    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 128
    arr[:, :, 1] = 64  # ~ -44.82 deg
    arr[:, :, 3] = 255
    img_path = tmp_path / "build_round.png"
    save_image_rgba(img_path, arr)

    design_unrounded = build_design(
        img_path,
        encoding_profile="rgba-continuous-v1",
        apply_filter=False,
        round_integer_angles=False,
    )
    assert not np.isclose(design_unrounded.angle_deg[0, 0], -45.0, atol=1e-3)

    design_rounded = build_design(
        img_path,
        encoding_profile="rgba-continuous-v1",
        apply_filter=False,
        round_integer_angles=True,
    )
    assert design_rounded.angle_deg[0, 0] == -45.0


def test_cli_round_angles(tmp_path: Path):
    """Verify CLI inspect and export accept --round-angles / --no-round-angles."""
    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 128
    arr[:, :, 1] = 64
    arr[:, :, 3] = 255
    img_path = tmp_path / "cli_round.png"
    save_image_rgba(img_path, arr)

    ret = cli_main([
        "inspect", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--round-angles",
    ])
    assert ret == 0

    ret_no = cli_main([
        "inspect", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--no-round-angles",
    ])
    assert ret_no == 0

    out_dir = tmp_path / "_OUT_ROUND"
    ret_exp = cli_main([
        "export", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--round-angles",
        "-o", str(out_dir),
        "--name", "ROUND_HOLO",
    ])
    assert ret_exp == 0

    out_preview = tmp_path / "preview_round.png"
    ret_prev = cli_main([
        "preview", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--round-angles",
        "-o", str(out_preview),
    ])
    assert ret_prev == 0
    assert out_preview.exists()

    out_preview_no = tmp_path / "preview_noround.png"
    ret_prev_no = cli_main([
        "preview", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--no-round-angles",
        "-o", str(out_preview_no),
    ])
    assert ret_prev_no == 0
    assert out_preview_no.exists()


def test_gui_logic_round_integer_angles(tmp_path: Path):
    """Verify load_gui_design respects round_integer_angles."""
    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 128
    arr[:, :, 1] = 64
    arr[:, :, 3] = 255
    img_path = tmp_path / "gui_round.png"
    save_image_rgba(img_path, arr)

    design = load_gui_design(
        img_path,
        image_format="RGBA continuous",
        pitch_um=20.0,
        apply_filter=False,
        round_integer_angles=True,
    )
    assert design.angle_deg[0, 0] == -45.0


def test_gui_design_window_round_angles_toggle(tmp_path: Path):
    """Verify toggling Round to Integer Angles checkbox in DesignWindow updates angle readout."""
    import time
    import tkinter as tk
    from dot_ebl_preview.gui import DesignWindow

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Desktop session unavailable: {error}")
    root.withdraw()

    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 128
    arr[:, :, 1] = 64  # ~ -44.82 deg
    arr[:, :, 3] = 255
    img_path = tmp_path / "gui_round_toggle.png"
    save_image_rgba(img_path, arr)

    win = None
    try:
        win = DesignWindow(root)
        win.path_var.set(str(img_path))
        win.format_var.set("RGBA continuous")
        win._load()

        deadline = time.monotonic() + 5.0
        while win.busy and time.monotonic() < deadline:
            win._poll_results()
            time.sleep(0.01)
        win._poll_results()

        assert win.design is not None
        assert not np.isclose(win.design.angle_deg[0, 0], -45.0, atol=1e-3)
        assert win.rgba_round_angles_var.get() is False

        # Toggle round angles to True and invoke handler
        win.rgba_round_angles_var.set(True)
        win._rgba_settings_changed()
        assert win.design.angle_deg[0, 0] == -45.0

        # Toggle round angles back to False and invoke handler
        win.rgba_round_angles_var.set(False)
        win._rgba_settings_changed()
        assert not np.isclose(win.design.angle_deg[0, 0], -45.0, atol=1e-3)
    finally:
        if win is not None:
            win._close()


def test_rgba_round_period_50nm_without_filter():
    """Verify active periods are rounded to 50 nm multiples when round_period_50nm is True."""
    # 4x1 image:
    # Pixel 0: R=5 -> 400 + 5/255 * 1200 = 423.53 nm -> rounded to 400 nm
    # Pixel 1: R=15 -> 400 + 15/255 * 1200 = 470.59 nm -> rounded to 450 nm
    # Pixel 2: R=25 -> 400 + 25/255 * 1200 = 517.65 nm -> rounded to 500 nm
    # Pixel 3: Inactive (A=0) -> remains 0
    arr = np.array([
        [[5, 128, 0, 255], [15, 128, 0, 255], [25, 128, 0, 255], [5, 128, 0, 0]]
    ], dtype=np.uint8)

    # Without rounding
    prof_raw = RGBAContinuousProfile(apply_filter=False, round_period_50nm=False)
    design_raw = prof_raw.decode(arr)
    assert design_raw.period_nm[0, 0] == 424
    assert design_raw.period_nm[0, 1] == 471
    assert design_raw.period_nm[0, 2] == 518
    assert design_raw.period_nm[0, 3] == 0

    # With rounding
    prof_rounded = RGBAContinuousProfile(apply_filter=False, round_period_50nm=True)
    design_rounded = prof_rounded.decode(arr)
    assert design_rounded.period_nm[0, 0] == 400
    assert design_rounded.period_nm[0, 1] == 450
    assert design_rounded.period_nm[0, 2] == 500
    assert design_rounded.period_nm[0, 3] == 0


def test_rgba_round_period_50nm_with_filter():
    """Verify rounding occurs after bilateral filtering so final periods are exact multiples of 50 nm."""
    arr = np.array([
        [[10, 128, 0, 255], [20, 128, 0, 255], [30, 128, 0, 255]]
    ], dtype=np.uint8)

    prof = RGBAContinuousProfile(apply_filter=True, round_period_50nm=True)
    design = prof.decode(arr)

    for c in range(3):
        period = design.period_nm[0, c]
        assert period % 50 == 0, f"Period {period} is not a multiple of 50 nm"
        assert period > 0


def test_build_design_round_period_50nm(tmp_path: Path):
    """Verify build_design respects round_period_50nm parameter."""
    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 5  # ~ 424 nm -> rounded to 400 nm
    arr[:, :, 1] = 128
    arr[:, :, 3] = 255
    img_path = tmp_path / "build_round_period.png"
    save_image_rgba(img_path, arr)

    design_unrounded = build_design(
        img_path,
        encoding_profile="rgba-continuous-v1",
        apply_filter=False,
        round_period_50nm=False,
    )
    assert design_unrounded.period_nm[0, 0] == 424

    design_rounded = build_design(
        img_path,
        encoding_profile="rgba-continuous-v1",
        apply_filter=False,
        round_period_50nm=True,
    )
    assert design_rounded.period_nm[0, 0] == 400


def test_cli_round_period_50nm(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Verify CLI inspect, export, and preview accept --round-period-50nm / --no-round-period-50nm."""
    import json
    from dot_ebl_preview.io.artifacts import load_design_artifact

    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 5
    arr[:, :, 1] = 128
    arr[:, :, 3] = 255
    img_path = tmp_path / "cli_round_period.png"
    save_image_rgba(img_path, arr)

    capsys.readouterr()
    ret = cli_main([
        "inspect", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--round-period-50nm",
    ])
    assert ret == 0
    out_json = json.loads(capsys.readouterr().out)
    assert out_json["unique_periods_nm"] == [400]

    ret_no = cli_main([
        "inspect", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--no-round-period-50nm",
    ])
    assert ret_no == 0
    out_json_no = json.loads(capsys.readouterr().out)
    assert out_json_no["unique_periods_nm"] == [424]

    out_dir = tmp_path / "_OUT_ROUND_PERIOD"
    ret_exp = cli_main([
        "export", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--round-period-50nm",
        "-o", str(out_dir),
        "--name", "ROUND_PERIOD_HOLO",
    ])
    assert ret_exp == 0
    bundle_dirs = list(out_dir.glob("*_ROUND_PERIOD_HOLO"))
    assert len(bundle_dirs) == 1
    exp_design = load_design_artifact(bundle_dirs[0] / "design.npz")
    assert exp_design.period_nm[0, 0] == 400

    out_dir_no = tmp_path / "_OUT_NO_ROUND_PERIOD"
    ret_exp_no = cli_main([
        "export", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--no-round-period-50nm",
        "-o", str(out_dir_no),
        "--name", "NOROUND_PERIOD_HOLO",
    ])
    assert ret_exp_no == 0
    bundle_dirs_no = list(out_dir_no.glob("*_NOROUND_PERIOD_HOLO"))
    assert len(bundle_dirs_no) == 1
    exp_design_no = load_design_artifact(bundle_dirs_no[0] / "design.npz")
    assert exp_design_no.period_nm[0, 0] == 424

    out_preview = tmp_path / "preview_round_period.png"
    ret_prev = cli_main([
        "preview", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--round-period-50nm",
        "-o", str(out_preview),
    ])
    assert ret_prev == 0
    assert out_preview.exists()

    out_preview_no = tmp_path / "preview_noround_period.png"
    ret_prev_no = cli_main([
        "preview", str(img_path),
        "--profile", "rgba-continuous-v1",
        "--no-round-period-50nm",
        "-o", str(out_preview_no),
    ])
    assert ret_prev_no == 0
    assert out_preview_no.exists()


def test_rgba_16bit_round_period_50nm():
    """Verify 16-bit RGBA decoding with round_period_50nm."""
    # Pixel 0: R=13653 -> 400 + (13653 / 65535) * 1200 = 650.003 nm -> rounded to 650 nm
    # Pixel 1: R=12000 -> 400 + (12000 / 65535) * 1200 = 619.72 nm -> rounded to 600 nm
    # Pixel 2: A=0 -> inactive -> 0
    arr = np.array([
        [[13653, 0, 0, 65535], [12000, 0, 0, 65535], [13653, 0, 0, 0]]
    ], dtype=np.uint16)

    prof = RGBAContinuousProfile(apply_filter=False, round_period_50nm=True)
    design = prof.decode(arr)
    assert design.period_nm[0, 0] == 650
    assert design.period_nm[0, 1] == 600
    assert design.period_nm[0, 2] == 0


def test_rgba_joint_round_period_and_angles():
    """Verify applying both round_period_50nm and round_integer_angles simultaneously."""
    arr = np.array([
        [[5, 64, 0, 255], [15, 191, 0, 255]]
    ], dtype=np.uint8)

    prof = RGBAContinuousProfile(
        apply_filter=False,
        round_period_50nm=True,
        round_integer_angles=True,
    )
    design = prof.decode(arr)
    assert design.period_nm[0, 0] == 400
    assert design.angle_deg[0, 0] == -45.0
    assert design.period_nm[0, 1] == 450
    assert design.angle_deg[0, 1] == 45.0


def test_gui_logic_round_period_50nm(tmp_path: Path):
    """Verify load_gui_design respects round_period_50nm."""
    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 5
    arr[:, :, 1] = 128
    arr[:, :, 3] = 255
    img_path = tmp_path / "gui_round_period.png"
    save_image_rgba(img_path, arr)

    design = load_gui_design(
        img_path,
        image_format="RGBA continuous",
        pitch_um=20.0,
        apply_filter=False,
        round_period_50nm=True,
    )
    assert design.period_nm[0, 0] == 400


def test_gui_design_window_round_period_toggle(tmp_path: Path):
    """Verify toggling Round Period to 50 nm checkbox in DesignWindow updates period readout."""
    import time
    import tkinter as tk
    from dot_ebl_preview.gui import DesignWindow

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Desktop session unavailable: {error}")
    root.withdraw()

    arr = np.zeros((2, 2, 4), dtype=np.uint8)
    arr[:, :, 0] = 5  # 424 nm -> rounded to 400 nm
    arr[:, :, 1] = 128
    arr[:, :, 3] = 255
    img_path = tmp_path / "gui_round_period_toggle.png"
    save_image_rgba(img_path, arr)

    win = None
    try:
        win = DesignWindow(root)
        win.path_var.set(str(img_path))
        win.format_var.set("RGBA continuous")
        win._load()

        deadline = time.monotonic() + 5.0
        while win.busy and time.monotonic() < deadline:
            win._poll_results()
            time.sleep(0.01)
        win._poll_results()

        assert win.design is not None
        assert win.design.period_nm[0, 0] != 400
        assert win.rgba_round_period_var.get() is False

        # Toggle round period to True and invoke handler
        win.rgba_round_period_var.set(True)
        win._rgba_settings_changed()
        assert win.design.period_nm[0, 0] == 400

        # Toggle round period back to False and invoke handler
        win.rgba_round_period_var.set(False)
        win._rgba_settings_changed()
        assert win.design.period_nm[0, 0] != 400
    finally:
        if win is not None:
            win._close()
