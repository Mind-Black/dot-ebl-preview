"""Tests for holopixel stripe geometry and 1 nm grid snapping."""

import numpy as np
from dot_ebl_preview.layout.holopixel import generate_holopixel_stripes


def test_holopixel_stripes_width_zero():
    paths, skipped = generate_holopixel_stripes(pitch_nm=20000, period_nm=1000)
    assert len(paths) > 0
    for p in paths:
        # Crucial requirement: single-pixel lines have width 0
        assert p.width_nm == 0
        assert len(p.vertices_nm) == 2
        (x1, y1), (x2, y2) = p.vertices_nm
        assert y1 == y2
        assert x1 == -x2
        assert x2 > 0  # Distinct endpoints


def test_holopixel_odd_period_half_grid_r4():
    """Critic Review R4: Test 20000 nm pitch with 903 nm odd period.

    Local stripe center start is -10000 + 451.5 = -9548.5 nm, which lands on a half-nanometre.
    Verify that half-away-from-zero snapping correctly produces integer coordinates
    and consistent spacing.
    """
    paths, skipped = generate_holopixel_stripes(pitch_nm=20000, period_nm=903)
    assert len(paths) > 0
    y_coords = [p.vertices_nm[0][1] for p in paths]

    # Verify all coordinates are integers
    for y in y_coords:
        assert isinstance(y, int)

    # Check spacing between consecutive stripes
    spacings = np.diff(y_coords)
    # Critic Review R4: MATLAB-style half-away-from-zero rounding creates
    # a 1-nm spacing difference across zero (904 nm), while all other steps are exactly 903 nm.
    assert np.all((spacings == 903) | (spacings == 904))
    # Exactly one 904 nm step across zero
    assert np.count_nonzero(spacings == 904) == 1
