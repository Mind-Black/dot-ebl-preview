"""Tests for bug fixes, edge cases, and numerical stability verified during code audit."""

import math
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from dot_ebl_preview.core.encoding import (
    RGB8IndexedProfile,
    RGB16FixedProfile,
)
from dot_ebl_preview.core.filters import (
    _lift_to_nearest_branch,
    apply_bilateral_filter,
    apply_gaussian_filter,
)
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.core.operations import apply_radial_gradient
from dot_ebl_preview.io.images import load_image_rgb, save_image_rgb
from dot_ebl_preview.io.legacy_unity import shader_rgb_to_hsv
from dot_ebl_preview.optics.engine import (
    OpticalSimParams,
    simulate_cell_optical_color,
)
from dot_ebl_preview.raith.elements import PathElement, SrefElement, sanitize_structure_name
from dot_ebl_preview.raith.records import (
    df_to_datatype,
    excess64_decode,
    excess64_encode,
    pack_gds_record,
)


def test_unity_shader_rgb_to_hsv_primaries():
    """Verify shader_rgb_to_hsv computes correct hues for all primary and secondary colors."""
    # Red: (1, 0, 0) -> H=0.0 (0 deg)
    h, s, v = shader_rgb_to_hsv(1.0, 0.0, 0.0)
    assert abs(h - 0.0) < 1e-4
    assert abs(s - 1.0) < 1e-4
    assert abs(v - 1.0) < 1e-4

    # Green: (0, 1, 0) -> H=1/3 (120 deg)
    h, s, v = shader_rgb_to_hsv(0.0, 1.0, 0.0)
    assert abs(h - (1.0 / 3.0)) < 1e-4
    assert abs(s - 1.0) < 1e-4
    assert abs(v - 1.0) < 1e-4

    # Blue: (0, 0, 1) -> H=2/3 (240 deg)
    h, s, v = shader_rgb_to_hsv(0.0, 0.0, 1.0)
    assert abs(h - (2.0 / 3.0)) < 1e-4
    assert abs(s - 1.0) < 1e-4
    assert abs(v - 1.0) < 1e-4

    # Yellow: (1, 1, 0) -> H=1/6 (60 deg)
    h, s, v = shader_rgb_to_hsv(1.0, 1.0, 0.0)
    assert abs(h - (1.0 / 6.0)) < 1e-4

    # Cyan: (0, 1, 1) -> H=0.5 (180 deg)
    h, s, v = shader_rgb_to_hsv(0.0, 1.0, 1.0)
    assert abs(h - 0.5) < 1e-4

    # Magenta: (1, 0, 1) -> H=5/6 (300 deg)
    h, s, v = shader_rgb_to_hsv(1.0, 0.0, 1.0)
    assert abs(h - (5.0 / 6.0)) < 1e-4


def test_16bit_rgb_png_lossless_roundtrip(tmp_path: Path):
    """Verify 16-bit RGB PNG saving and loading without loss of precision or Pillow errors."""
    rng = np.random.default_rng(42)
    arr_16 = rng.integers(0, 65536, size=(8, 12, 3), dtype=np.uint16)

    img_path = tmp_path / "test_16bit_roundtrip.png"
    save_image_rgb(img_path, arr_16)
    assert img_path.exists()

    loaded = load_image_rgb(img_path)
    assert loaded.dtype == np.uint16
    assert loaded.shape == (8, 12, 3)
    assert np.array_equal(loaded, arr_16)


def test_rgb16_profile_max_period_bounds():
    """Verify RGB16FixedProfile rejects max_period_nm > 65535 and periods > 65535."""
    # Profile definition rejection
    with pytest.raises(ValueError, match="cannot exceed 65535"):
        RGB16FixedProfile(max_period_nm=70000)

    # Encoding rejection for periods > max_period_nm
    prof = RGB16FixedProfile()
    assert prof.max_period_nm == 65535

    # Period 70000 nm exceeds uint16
    p = np.array([[70000]], dtype=np.uint32)
    a = np.array([[0.0]], dtype=np.float64)
    act = np.array([[True]], dtype=np.bool_)
    des = Design(shape=(1, 1), pitch_nm=20000, period_nm=p, angle_deg=a, active=act)

    with pytest.raises(ValueError, match="Periods outside bounds"):
        prof.encode(des)


def test_excess64_overflow_detection():
    """Verify excess64_encode raises OverflowError when exponent exceeds 7 bits."""
    # Extremely large number (1e76 exceeds real8 capacity of ~1e75)
    with pytest.raises(OverflowError, match="out of GDS real8 bounds"):
        excess64_encode(1e76)

    with pytest.raises(OverflowError, match="out of GDS real8 bounds"):
        excess64_encode(-1e76)


def test_lift_to_nearest_branch_extended_range():
    """Verify _lift_to_nearest_branch handles angles far outside [-180, +180]."""
    # 550°: closest branch to 10° is 10 + 3*180 = 550°
    assert _lift_to_nearest_branch(10.0, 550.0) == 550.0

    # -600°: closest branch to 0° is 0 - 3*180 = -540 or 0 - 4*180 = -720
    # diff to -540 is 60, diff to -720 is 120 -> -540°
    assert _lift_to_nearest_branch(0.0, -600.0) == -540.0


def test_filter_zero_and_negative_sigma():
    """Verify Gaussian and bilateral filters handle zero or negative sigma without division by zero."""
    shape = (3, 3)
    p = np.full(shape, 1000, dtype=np.uint32)
    a = np.zeros(shape, dtype=np.float64)
    act = np.ones(shape, dtype=np.bool_)
    des = Design(shape=shape, pitch_nm=20000, period_nm=p, angle_deg=a, active=act)

    # Gaussian with sigma <= 0 or radius <= 0
    res_g1 = apply_gaussian_filter(des, sigma=0.0)
    assert np.array_equal(res_g1.angle_deg, a)

    res_g2 = apply_gaussian_filter(des, sigma=1.0, radius=0)
    assert np.array_equal(res_g2.angle_deg, a)

    # Bilateral with sigma_color <= 0 or sigma_space <= 0
    res_b1 = apply_bilateral_filter(des, sigma_color=0.0)
    assert np.array_equal(res_b1.angle_deg, a)

    res_b2 = apply_bilateral_filter(des, sigma_space=-1.0)
    assert np.array_equal(res_b2.angle_deg, a)


def test_nan_dose_and_mag_rejections():
    """Verify NaN and Inf are rejected in Design, elements, and dose conversion."""
    # df_to_datatype with NaN
    with pytest.raises(ValueError, match="finite"):
        df_to_datatype(float("nan"))

    with pytest.raises(ValueError, match="finite"):
        df_to_datatype(float("inf"))

    # Design with NaN dose
    shape = (1, 1)
    p = np.array([[1000]], dtype=np.uint32)
    a = np.array([[0.0]], dtype=np.float64)
    act = np.array([[True]], dtype=np.bool_)
    with pytest.raises(ValueError, match="dose factor must be non-negative finite"):
        Design(shape=shape, pitch_nm=20000, period_nm=p, angle_deg=a, active=act, dose=float("nan"))

    # PathElement with NaN dose
    with pytest.raises(ValueError, match="Dose factor must be a finite number"):
        PathElement(layer=1, vertices_nm=[(0, 0), (1000, 0)], df=float("nan"))

    # SrefElement with NaN magnification
    with pytest.raises(ValueError, match="SREF magnification must be positive finite"):
        SrefElement(name="CELL", origin_nm=(0, 0), mag=float("nan"))


def test_design_region_mask_shape_validation():
    """Verify Design.validate() rejects region masks with mismatching shapes."""
    shape = (2, 2)
    p = np.full(shape, 1000, dtype=np.uint32)
    a = np.zeros(shape, dtype=np.float64)
    act = np.ones(shape, dtype=np.bool_)

    bad_mask = np.ones((3, 3), dtype=np.bool_)
    with pytest.raises(ValueError, match="region_mask 'test' shape"):
        Design(
            shape=shape,
            pitch_nm=20000,
            period_nm=p,
            angle_deg=a,
            active=act,
            region_masks={"test": bad_mask},
        )


def test_apply_radial_gradient_mask_shape_validation():
    """Verify apply_radial_gradient raises ValueError on mismatching mask shape."""
    shape = (2, 2)
    p = np.full(shape, 1000, dtype=np.uint32)
    a = np.zeros(shape, dtype=np.float64)
    act = np.ones(shape, dtype=np.bool_)
    des = Design(shape=shape, pitch_nm=20000, period_nm=p, angle_deg=a, active=act)

    bad_mask = np.ones((4, 4), dtype=np.bool_)
    with pytest.raises(ValueError, match="Mask shape"):
        apply_radial_gradient(des, mask=bad_mask)


def test_sanitize_structure_name_zero_or_negative_maxlen():
    """Verify sanitize_structure_name handles non-positive max_len cleanly."""
    assert sanitize_structure_name("MyStructure", max_len=0) == "MyStructure"
    assert sanitize_structure_name("MyStructure", max_len=-5) == "MyStructure"
    assert sanitize_structure_name("???", max_len=10) == "___"
