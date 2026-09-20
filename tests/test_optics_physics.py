"""Physical regression checks for the geometric optical preview."""

import math

import numpy as np

from dot_ebl_preview.optics.engine import OpticalSimParams, simulate_cell_optical_color
from dot_ebl_preview.optics.tables import XYZ2RGB


def test_d65_white_maps_to_neutral_linear_srgb():
    d65_xyz = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    np.testing.assert_allclose(XYZ2RGB() @ d65_xyz, [1.0, 1.0, 1.0], atol=1e-3)


def test_zero_degree_grating_is_yellow_green_and_ninety_degree_is_dark():
    on_axis = np.asarray(simulate_cell_optical_color(1000, 0.0))
    cross_axis = np.asarray(simulate_cell_optical_color(1000, 90.0))
    assert on_axis[1] > 0.005
    assert on_axis[1] > 0.6 * on_axis[0]
    assert np.max(cross_axis) < 1e-8


def test_positive_rotation_matches_layout_grating_vector():
    # Illuminate along the +Y stripe normal after a 30-degree CCW SREF
    # rotation: K = (-sin(30), cos(30)). Only the +1 order is selected.
    rotation = math.radians(30.0)
    incidence = math.radians(35.0)
    light = (
        -36.0 * math.sin(incidence) * math.sin(rotation),
        36.0 * math.sin(incidence) * math.cos(rotation),
        36.0 * math.cos(incidence),
    )
    params = OpticalSimParams(orders=(1,), light_pos=light, camera_pos=(0.0, 0.0, 66.0),
                              aperture_radius_factor=1.0, source_radius_factor=0.0)
    aligned = np.asarray(simulate_cell_optical_color(1000, 30.0, params=params))
    reversed_rotation = np.asarray(simulate_cell_optical_color(1000, -30.0, params=params))
    assert aligned.sum() > 0.05
    assert reversed_rotation.sum() < 1e-8


def test_finite_cell_avoids_binary_spectral_dropout():
    params = OpticalSimParams(aperture_radius_factor=0.01)
    centered = np.asarray(simulate_cell_optical_color(1000, 0.0, params=params))
    offset_params = OpticalSimParams(camera_pos=(1.0, 0.0, 300.0), aperture_radius_factor=0.01)
    offset = np.asarray(simulate_cell_optical_color(1000, 0.0, params=offset_params))
    assert centered.sum() > 0.0
    assert 0.0 < offset.sum() < centered.sum()


def test_far_field_aperture_collection_approaches_inverse_square():
    near = np.asarray(simulate_cell_optical_color(
        1000, 0.0, params=OpticalSimParams(camera_pos=(0.0, 0.0, 1000.0)),
    ))
    far = np.asarray(simulate_cell_optical_color(
        1000, 0.0, params=OpticalSimParams(camera_pos=(0.0, 0.0, 2000.0)),
    ))
    assert near.sum() > 0.0
    assert 0.2 < far.sum() / near.sum() < 0.3


def test_illumination_from_below_substrate_is_dark():
    params = OpticalSimParams(light_pos=(0.0, 20.0, -30.0))
    assert simulate_cell_optical_color(1000, 0.0, params=params) == (0.0, 0.0, 0.0)
