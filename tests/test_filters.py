"""Tests for smoothing filters and axial branch unwrapping (Critic Review R2)."""

import numpy as np
from dot_ebl_preview.core.filters import (
    _lift_to_nearest_branch,
    apply_bilateral_filter,
    apply_gaussian_filter,
)
from dot_ebl_preview.core.model import Design


def test_lift_to_nearest_branch():
    # Axial angle is 10 deg (representing 10 or 190 or -170 deg)
    # Original angle is 185 deg -> closest branch is 10 + 180 = 190 deg
    assert _lift_to_nearest_branch(10.0, 185.0) == 190.0

    # Original angle is -175 deg -> closest branch is 10 - 180 = -170 deg
    assert _lift_to_nearest_branch(10.0, -175.0) == -170.0

    # Deterministic tie-breaking: original angle is 90 deg, axial is 0 deg
    # Branches 0 and 180 are equidistant (distance 90)
    # Tie broken by choosing numerically lower branch: 0.0
    assert _lift_to_nearest_branch(0.0, 90.0) == 0.0


def test_axial_gaussian_preserves_directed_branch_r2():
    # Check that angles around -85 and +85 deg smooth properly without arbitrary 180-deg phase flips
    shape = (1, 5)
    period_nm = np.full(shape, 900, dtype=np.uint32)
    # Angles near -90 degrees
    angle_deg = np.array([[-88.0, -89.0, -90.0, -91.0, -92.0]], dtype=np.float64)
    active = np.ones(shape, dtype=np.bool_)

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
    filtered = apply_gaussian_filter(design, sigma=1.0, mode="axial")

    # The middle pixel (-90.0) should remain near -90.0 (e.g. within [-92, -88]), not flipped to +90.0!
    assert -95.0 <= filtered.angle_deg[0, 2] <= -85.0


def test_gaussian_masked_valid_only():
    # Inactive neighbors should not pull down valid angles
    shape = (3, 3)
    period_nm = np.full(shape, 1000, dtype=np.uint32)
    angle_deg = np.full(shape, 45.0, dtype=np.float64)
    active = np.zeros(shape, dtype=np.bool_)
    active[1, 1] = True  # Only center is active

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
    filtered = apply_gaussian_filter(design, sigma=1.0, mode="scalar")

    # Center value should remain 45.0
    assert abs(filtered.angle_deg[1, 1] - 45.0) < 1e-6
