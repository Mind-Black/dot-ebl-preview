"""Tests for CPU optical reference engine and spectral tables."""

import numpy as np
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.optics.engine import (
    render_optical_preview,
    simulate_cell_optical_color,
)
from dot_ebl_preview.optics.presets import get_optical_preset
from dot_ebl_preview.optics.tables import (
    XYZ2RGB,
    period_real,
    premultiplied_XYZ,
    reflNi,
    s2xyz,
    specIntens,
    stdIllum,
)


def test_spectral_tables_dimensions_and_finite():
    s_xyz = s2xyz()
    assert s_xyz.shape == (3, 77)
    assert np.all(np.isfinite(s_xyz))

    illum = stdIllum()
    assert illum.shape == (77,)
    assert np.all(np.isfinite(illum))

    refl = reflNi()
    assert refl.shape == (77,)
    assert np.all(np.isfinite(refl))

    intens = specIntens()
    assert intens.shape == (77,)
    assert np.all(np.isfinite(intens))

    pre_xyz = premultiplied_XYZ()
    assert pre_xyz.shape == (77, 3)
    assert np.all(np.isfinite(pre_xyz))

    mat = XYZ2RGB()
    assert mat.shape == (3, 3)
    assert np.all(np.isfinite(mat))


def test_optical_color_simulation_valid():
    # Test valid grating period (e.g. 1000 nm, 0 deg)
    r, g, b = simulate_cell_optical_color(period_nm=1000, angle_deg=0.0)
    assert 0.0 <= r <= 1.0
    assert 0.0 <= g <= 1.0
    assert 0.0 <= b <= 1.0


def test_optical_color_simulation_inactive_zero():
    # Period 0 should return strictly zero RGB
    r, g, b = simulate_cell_optical_color(period_nm=0, angle_deg=0.0)
    assert r == 0.0
    assert g == 0.0
    assert b == 0.0


def test_render_optical_preview():
    shape = (4, 4)
    period_nm = np.full(shape, 1000, dtype=np.uint32)
    angle_deg = np.zeros(shape, dtype=np.float64)
    active = np.ones(shape, dtype=np.bool_)
    active[0, 0] = False  # Inactive pixel

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
    img_float = render_optical_preview(design)

    assert img_float.shape == (4, 4, 3)
    assert np.all(np.isfinite(img_float))
    # Inactive cell without fallback should be black
    assert np.all(img_float[0, 0] == 0.0)
