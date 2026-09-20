"""Tests for legacy importers (OpenCV HLS and Unity HSV) and persistence."""

from pathlib import Path
import numpy as np
from PIL import Image

from dot_ebl_preview.io.artifacts import load_design_artifact, save_design_artifact
from dot_ebl_preview.io.legacy_hls import import_legacy_hls
from dot_ebl_preview.io.legacy_unity import (
    get_unity_grating_nm,
    import_legacy_unity_hsv,
    shader_rgb_to_hsv,
)


def test_unity_hsv_thresholds_and_ties():
    # Saturation < 0.1 disables grating
    assert get_unity_grating_nm(h=0.5, s=0.05) == 0

    # Hue > 0.7 maps to period_real[0] = 1328 nm
    assert get_unity_grating_nm(h=0.75, s=0.5) == 1328

    # Equal distance ties between hues
    # laser_hues[0] is 6/360 = 0.016666... and laser_hues[1] is 25/360 = 0.069444...
    # Midpoint is (6 + 25) / 720 = 31 / 720
    mid = 31.0 / 720.0
    # Strict inequality diff < closest gives index 0 (first entry) on equal distance
    assert get_unity_grating_nm(h=mid, s=0.5) == 1328


def test_unity_import_with_fallback(tmp_path: Path):
    # Create test image with one bright pixel and one dim pixel
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    # Dim pixel: (50, 50, 50) -> mean = 50 / 255.0 = 0.196
    # Fallback should be mean / 5 = ~0.0392
    img[0, 0] = [50, 50, 50]
    # Saturated green pixel (hue ~ 120/360 = 0.333, sat = 1.0)
    img[0, 1] = [0, 255, 0]

    img_path = tmp_path / "test_unity.png"
    Image.fromarray(img).save(img_path)

    design = import_legacy_unity_hsv(img_path)
    assert design.shape == (2, 2)
    assert design.fallback_intensity is not None

    expected_fb = (50.0 / 255.0) / 5.0
    assert abs(design.fallback_intensity[0, 0] - expected_fb) < 1e-4


def test_design_artifact_persistence(tmp_path: Path):
    shape = (3, 3)
    period_nm = np.array([[900, 1000, 1100], [1200, 903, 1000], [900, 0, 1100]], dtype=np.uint32)
    angle_deg = np.array([[-10.0, 0.0, 10.0], [20.0, -30.0, 45.0], [90.0, 0.0, -45.0]], dtype=np.float64)
    active = np.array([[True, True, True], [True, True, True], [True, False, True]], dtype=np.bool_)

    from dot_ebl_preview.core.model import Design

    orig = Design(
        shape=shape,
        pitch_nm=20000,
        period_nm=period_nm,
        angle_deg=angle_deg,
        active=active,
        source_identity="test_design",
    )

    npz_path = tmp_path / "design.npz"
    save_design_artifact(npz_path, orig)
    assert npz_path.exists()

    loaded = load_design_artifact(npz_path)
    assert loaded.shape == orig.shape
    assert loaded.pitch_nm == orig.pitch_nm
    assert np.array_equal(loaded.period_nm, orig.period_nm)
    assert np.array_equal(loaded.angle_deg, orig.angle_deg)
    assert np.array_equal(loaded.active, orig.active)
    assert loaded.source_identity == orig.source_identity
