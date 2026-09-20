"""Tests for RGB parameter encoding and decoding contracts."""

import numpy as np
import pytest

from dot_ebl_preview.core.encoding import (
    RGB8IndexedProfile,
    RGB16FixedProfile,
    round_half_away_from_zero,
)
from dot_ebl_preview.core.model import Design


def test_round_half_away_from_zero():
    assert round_half_away_from_zero(0.5) == 1
    assert round_half_away_from_zero(-0.5) == -1
    assert round_half_away_from_zero(1.4) == 1
    assert round_half_away_from_zero(1.5) == 2
    assert round_half_away_from_zero(-1.5) == -2


def test_rgb8_exact_roundtrip():
    profile = RGB8IndexedProfile()
    # Create test design with known LUT values
    # R=0 -> 900 nm, R=10 -> 1000 nm, R=30 -> 1200 nm
    # G=0 -> -90 deg, G=90 -> 0 deg, G=180 -> +90 deg
    shape = (2, 2)
    period_nm = np.array([[900, 1000], [1200, 900]], dtype=np.uint32)
    angle_deg = np.array([[-90.0, 0.0], [90.0, -45.0]], dtype=np.float64)
    active = np.array([[True, True], [True, False]], dtype=np.bool_)

    design = Design(
        shape=shape,
        pitch_nm=20000,
        period_nm=period_nm,
        angle_deg=angle_deg,
        active=active,
    )

    img, report = profile.encode(design, policy="reject")
    assert report.verified is True
    assert report.unrepresentable_count == 0
    assert report.max_period_error_nm == 0.0
    assert report.max_angle_error_deg == 0.0

    # Inactive pixel B must be 0
    assert img[1, 1, 2] == 0
    # Active pixels B must be 255
    assert img[0, 0, 2] == 255

    decoded = profile.decode(img, pitch_nm=20000)
    assert np.array_equal(decoded.active, active)
    assert np.array_equal(decoded.period_nm[active], period_nm[active])
    assert np.allclose(decoded.angle_deg[active], angle_deg[active])


def test_rgb8_reject_policy_on_offgrid():
    profile = RGB8IndexedProfile()
    # 905 nm is off-grid for default 10 nm step LUT
    period_nm = np.array([[905]], dtype=np.uint32)
    angle_deg = np.array([[0.0]], dtype=np.float64)
    active = np.array([[True]], dtype=np.bool_)

    design = Design(shape=(1, 1), pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)

    with pytest.raises(ValueError, match="cannot be represented exactly"):
        profile.encode(design, policy="reject")


def test_rgb8_quantize_policy_and_tie_breaking():
    profile = RGB8IndexedProfile()
    # 905 nm is exactly halfway between 900 (idx 0) and 910 (idx 1)
    # Lowest index wins tie -> index 0 (900 nm)
    period_nm = np.array([[905]], dtype=np.uint32)
    # 0.5 deg is halfway between 0 deg (idx 90) and 1 deg (idx 91)
    # Lowest index wins tie -> index 90 (0 deg)
    angle_deg = np.array([[0.5]], dtype=np.float64)
    active = np.array([[True]], dtype=np.bool_)

    design = Design(shape=(1, 1), pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)

    img, report = profile.encode(design, policy="quantize")
    assert report.unrepresentable_count == 2
    assert report.max_period_error_nm == 5.0
    assert report.max_angle_error_deg == 0.5

    assert img[0, 0, 0] == 0  # 900 nm
    assert img[0, 0, 1] == 90  # 0 deg


def test_rgb8_reserved_b_channel_error():
    profile = RGB8IndexedProfile()
    # B = 128 is reserved
    img = np.zeros((1, 1, 3), dtype=np.uint8)
    img[0, 0, 2] = 128
    with pytest.raises(ValueError, match="Reserved B channel values"):
        profile.decode(img)


def test_rgb16_roundtrip():
    profile = RGB16FixedProfile()
    shape = (2, 2)
    period_nm = np.array([[903, 1150], [1328, 900]], dtype=np.uint32)
    angle_deg = np.array([[-12.34, 45.67], [89.99, -90.00]], dtype=np.float64)
    active = np.array([[True, True], [True, False]], dtype=np.bool_)

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)

    img, report = profile.encode(design, policy="reject")
    assert report.verified is True
    assert report.unrepresentable_count == 0

    decoded = profile.decode(img, pitch_nm=20000)
    assert np.array_equal(decoded.active, active)
    assert np.array_equal(decoded.period_nm[active], period_nm[active])
    assert np.allclose(decoded.angle_deg[active], angle_deg[active], atol=1e-2)
