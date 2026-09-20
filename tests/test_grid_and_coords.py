"""Tests for coordinate system, pixel pitch, and extents."""

import numpy as np
from dot_ebl_preview.core.grid import (
    cell_center_nm,
    centered_preview_offset_nm,
    design_extents_nm,
    grid_centers_nm,
)


def test_cell_center_nm():
    # Pitch 20000 nm = 20 µm
    # row=0, col=0 -> x=(0+0.5)*20000 = 10000, y=-(0+0.5)*20000 = -10000
    x, y = cell_center_nm(0, 0, pitch_nm=20000)
    assert x == 10000
    assert y == -10000

    # row=1, col=2 -> x=(2+0.5)*20000 = 50000, y=-(1+0.5)*20000 = -30000
    x, y = cell_center_nm(1, 2, pitch_nm=20000)
    assert x == 50000
    assert y == -30000


def test_odd_pitch_half_grid_snap():
    # Odd pitch: 20001 nm
    # row=0, col=0 -> x = 0.5 * 20001 = 10000.5 -> snaps to 10001
    # y = -10000.5 -> snaps to -10001 (half away from zero)
    x, y = cell_center_nm(0, 0, pitch_nm=20001, snap=True)
    assert x == 10001
    assert y == -10001


def test_extents_and_preview_offset():
    extents = design_extents_nm(height=10, width=20, pitch_nm=20000)
    assert extents.x_min_nm == 0
    assert extents.x_max_nm == 400000
    assert extents.y_min_nm == -200000
    assert extents.y_max_nm == 0
    assert extents.width_nm == 400000
    assert extents.height_nm == 200000

    offset_x, offset_y = centered_preview_offset_nm(height=10, width=20, pitch_nm=20000)
    assert offset_x == -200000.0
    assert offset_y == 100000.0
