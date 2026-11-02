"""Generate deterministic synthetic test fixtures for the Web Preview Platform test suite.

Writes small, self-contained PNG inputs, .npz archives, and expected numerical arrays
into web/tests/fixtures/.
"""

import json
from pathlib import Path
import numpy as np
from PIL import Image

from dot_ebl_preview.core.encoding import RGB8IndexedProfile, RGB16FixedProfile
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.gui_logic import SceneSettings, render_scene
from dot_ebl_preview.io.artifacts import save_design_artifact
from dot_ebl_preview.io.images import save_image_rgb
from dot_ebl_preview.io.legacy_hls import import_legacy_hls
from dot_ebl_preview.io.legacy_unity import import_legacy_unity_hsv
from dot_ebl_preview.optics.tables import (
    XYZ2RGB,
    premultiplied_XYZ,
    reflNi,
    s2xyz,
    stdIllum,
)


def generate_all_fixtures() -> None:
    fixtures_dir = Path("web/tests/fixtures")
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Spectral Tables
    s_xyz = s2xyz()  # (3, 77)
    pre_xyz = premultiplied_XYZ()  # (77, 3)
    illum = stdIllum()  # (77,)
    ni = reflNi()  # (77,)
    xyz2rgb = XYZ2RGB()  # (3, 3)

    spectral_data = {
        "s2xyz": s_xyz.tolist(),
        "premultiplied_XYZ": pre_xyz.tolist(),
        "stdIllum": illum.tolist(),
        "reflNi": ni.tolist(),
        "XYZ2RGB": xyz2rgb.tolist(),
    }
    with open(fixtures_dir / "spectral_tables.json", "w") as f:
        json.dump(spectral_data, f, indent=2)

    # 2. RGB8 Indexed Fixture
    shape_rgb8 = (4, 4)
    periods_rgb8 = np.array([
        [900, 950, 1000, 1050],
        [1100, 1150, 1200, 900],
        [950, 1000, 1050, 1100],
        [1150, 1200, 900, 950],
    ], dtype=np.uint32)
    angles_rgb8 = np.array([
        [-90.0, -45.0, 0.0, 45.0],
        [90.0, -30.0, 30.0, -60.0],
        [60.0, -15.0, 15.0, -75.0],
        [75.0, 0.0, -45.0, 45.0],
    ], dtype=np.float64)
    active_rgb8 = np.ones(shape_rgb8, dtype=bool)
    active_rgb8[0, 0] = False
    active_rgb8[3, 3] = False
    periods_rgb8[~active_rgb8] = 0
    angles_rgb8[~active_rgb8] = 0.0

    design_rgb8 = Design(
        shape=shape_rgb8,
        pitch_nm=20000,
        period_nm=periods_rgb8,
        angle_deg=angles_rgb8,
        active=active_rgb8,
    )
    img_rgb8, _ = RGB8IndexedProfile().encode(design_rgb8)
    save_image_rgb(fixtures_dir / "rgb8_test.png", img_rgb8)

    with open(fixtures_dir / "rgb8_expected.json", "w") as f:
        json.dump({
            "shape": list(shape_rgb8),
            "pitch_nm": 20000,
            "period_nm": periods_rgb8.tolist(),
            "angle_deg": angles_rgb8.tolist(),
            "active": active_rgb8.astype(int).tolist(),
        }, f, indent=2)

    # 3. RGB16 Fixed Fixture
    shape_rgb16 = (4, 4)
    periods_rgb16 = np.array([
        [100, 500, 1000, 2500],
        [5000, 10000, 20000, 50000],
        [65535, 1000, 1200, 1400],
        [1600, 1800, 2000, 2200],
    ], dtype=np.uint32)
    angles_rgb16 = np.array([
        [0.0, 12.34, -45.67, 90.0],
        [-90.0, 180.0, -180.0, 270.55],
        [-327.68, 327.67, 0.01, -0.01],
        [5.55, -5.55, 45.0, -45.0],
    ], dtype=np.float64)
    active_rgb16 = np.ones(shape_rgb16, dtype=bool)
    active_rgb16[1, 1] = False
    periods_rgb16[~active_rgb16] = 0
    angles_rgb16[~active_rgb16] = 0.0

    design_rgb16 = Design(
        shape=shape_rgb16,
        pitch_nm=20000,
        period_nm=periods_rgb16,
        angle_deg=angles_rgb16,
        active=active_rgb16,
    )
    img_rgb16, _ = RGB16FixedProfile().encode(design_rgb16, policy="quantize")
    save_image_rgb(fixtures_dir / "rgb16_test.png", img_rgb16)

    with open(fixtures_dir / "rgb16_expected.json", "w") as f:
        json.dump({
            "shape": list(shape_rgb16),
            "pitch_nm": 20000,
            "period_nm": periods_rgb16.tolist(),
            "angle_deg": angles_rgb16.tolist(),
            "active": active_rgb16.astype(int).tolist(),
        }, f, indent=2)

    # 4. NPZ Design Archive Fixture
    save_design_artifact(fixtures_dir / "design.npz", design_rgb16)

    # 5. HLS Test Fixture
    # Create synthetic image with specific RGB colors:
    # Row 0: Red, Green, Blue, Black (L=0)
    # Row 1: White (L=255), Hue-162 cell, Gray, Yellow
    hls_rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    hls_rgb[0, 0] = [255, 0, 0]    # Red
    hls_rgb[0, 1] = [0, 255, 0]    # Green
    hls_rgb[0, 2] = [0, 0, 255]    # Blue
    hls_rgb[0, 3] = [0, 0, 0]      # Black (inactive)
    hls_rgb[1, 0] = [255, 255, 255] # White (inactive)
    hls_rgb[1, 1] = [212, 128, 170] # Hue 81 (2*H = 162 in OpenCV HLS)
    hls_rgb[1, 2] = [128, 128, 128] # Gray
    hls_rgb[1, 3] = [255, 255, 0]   # Yellow
    hls_rgb[2, :] = [100, 150, 200]
    hls_rgb[3, :] = [50, 100, 150]

    im_hls = Image.fromarray(hls_rgb, mode="RGB")
    im_hls.save(fixtures_dir / "hls_test.png")

    hls_design = import_legacy_hls(fixtures_dir / "hls_test.png", preset="holtida-ebl", mode="corrected", apply_radial=True)
    with open(fixtures_dir / "hls_expected.json", "w") as f:
        json.dump({
            "shape": list(hls_design.shape),
            "pitch_nm": hls_design.pitch_nm,
            "period_nm": hls_design.period_nm.tolist(),
            "angle_deg": hls_design.angle_deg.tolist(),
            "active": hls_design.active.astype(int).tolist(),
        }, f, indent=2)

    # 6. Unity HSV Test Fixture
    unity_rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    unity_rgb[0, 0] = [255, 50, 50]  # high saturation
    unity_rgb[0, 1] = [50, 255, 50]
    unity_rgb[0, 2] = [50, 50, 255]
    unity_rgb[0, 3] = [128, 128, 128] # saturation < 0.1 (inactive)
    unity_rgb[1, 0] = [200, 100, 50]
    unity_rgb[1, 1] = [255, 0, 128]
    unity_rgb[1, 2] = [0, 200, 200]
    unity_rgb[1, 3] = [100, 100, 100] # inactive
    unity_rgb[2, :] = [180, 220, 80]
    unity_rgb[3, :] = [40, 180, 220]

    im_unity = Image.fromarray(unity_rgb, mode="RGB")
    im_unity.save(fixtures_dir / "unity_test.png")

    unity_design = import_legacy_unity_hsv(fixtures_dir / "unity_test.png")
    with open(fixtures_dir / "unity_expected.json", "w") as f:
        json.dump({
            "shape": list(unity_design.shape),
            "pitch_nm": unity_design.pitch_nm,
            "period_nm": unity_design.period_nm.tolist(),
            "angle_deg": unity_design.angle_deg.tolist(),
            "active": unity_design.active.astype(int).tolist(),
        }, f, indent=2)

    # 7. Optical Reference Preview Fixture (matching test_gl_preview.py)
    shape_opt = (6, 6)
    periods_opt = np.tile(np.array([900, 950, 1000, 1050, 1100, 1150], dtype=np.uint32), (6, 1))
    angles_opt = np.zeros(shape_opt, dtype=np.float64)
    angles_opt[:, 2] = 4.0
    angles_opt[:, 3] = -4.0
    active_opt = np.ones(shape_opt, dtype=bool)
    active_opt[0, 0] = False
    fallback_opt = np.zeros(shape_opt, dtype=np.float32)
    fallback_opt[0, 0] = 0.2

    opt_design = Design(
        shape=shape_opt,
        pitch_nm=20000,
        period_nm=periods_opt,
        angle_deg=angles_opt,
        active=active_opt,
        fallback_intensity=fallback_opt,
    )
    opt_scene = SceneSettings(
        light_pos=(0.0, 20.6487533, 29.4891314),
        camera_pos=(0.3, 0.0, 66.0),
        orientation_deg=2.0,
        aperture_mm=5.0,
        source_size_mm=0.0,
    )
    rendered_img = render_scene(opt_design, opt_scene)
    rendered_rgb = np.asarray(rendered_img, dtype=np.uint8)
    save_image_rgb(fixtures_dir / "optical_reference.png", rendered_rgb)

    with open(fixtures_dir / "optical_reference_expected.json", "w") as f:
        json.dump({
            "shape": list(shape_opt),
            "pitch_nm": 20000,
            "period_nm": periods_opt.tolist(),
            "angle_deg": angles_opt.tolist(),
            "active": active_opt.astype(int).tolist(),
            "fallback_intensity": fallback_opt.tolist(),
            "scene": {
                "light_pos": list(opt_scene.light_pos),
                "camera_pos": list(opt_scene.camera_pos),
                "orientation_deg": opt_scene.orientation_deg,
                "aperture_mm": opt_scene.aperture_mm,
                "source_size_mm": opt_scene.source_size_mm,
            },
            "rgb_values": rendered_rgb.tolist(),
        }, f, indent=2)

    print("Successfully generated all synthetic fixtures into web/tests/fixtures/")


if __name__ == "__main__":
    generate_all_fixtures()
