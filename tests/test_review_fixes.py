"""Regression tests covering all 5 findings from docs/MVP_IMPLEMENTATION_REVIEW.md.

Findings verified:
  1. [P1] Preserve existing bundles on timestamp collisions (jobs/bundle.py).
  2. [P1] Preserve each legacy preset's default pitch (cli.py & legacy_unity.py).
  3. [P2] Evaluate optics at each cell's physical position (optics/engine.py).
  4. [P2] Round signed angles before adding RGB16 offset (core/encoding.py).
  5. [P2] Convert linear RGB to display sRGB before saving previews (preview/renderer.py).
"""

from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from dot_ebl_preview.cli import main as cli_main
from dot_ebl_preview.core.encoding import RGB16FixedProfile
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.io.artifacts import load_design_artifact
from dot_ebl_preview.io.legacy_hls import import_legacy_hls
from dot_ebl_preview.io.legacy_unity import import_legacy_unity_hsv
from dot_ebl_preview.jobs.bundle import stage_and_export_bundle
from dot_ebl_preview.optics.engine import render_optical_preview, simulate_cell_optical_color
from dot_ebl_preview.preview.renderer import linear_to_srgb, render_preview_to_file


# ---------------------------------------------------------------------------
# Finding 1: Preserve existing bundles on timestamp collisions
# ---------------------------------------------------------------------------

def test_bundle_collision_preserves_existing_bundle(tmp_path: Path):
    """Verify that export collisions do not delete prior completed bundles or their contents."""
    shape = (2, 2)
    period1 = np.full(shape, 1000, dtype=np.uint32)
    period2 = np.full(shape, 1200, dtype=np.uint32)
    angle = np.zeros(shape, dtype=np.float64)
    active = np.ones(shape, dtype=np.bool_)

    design1 = Design(shape=shape, pitch_nm=20000, period_nm=period1, angle_deg=angle, active=active)
    design2 = Design(shape=shape, pitch_nm=20000, period_nm=period2, angle_deg=angle, active=active)

    # First export
    dir1 = stage_and_export_bundle(design1, output_parent_dir=tmp_path, layout_name="COLLISION_HOLO")
    assert dir1.exists()

    # Place a marker file inside the completed bundle
    marker_file = dir1 / "marker.txt"
    marker_file.write_text("preserved_content", encoding="utf-8")

    # Second export with the exact same layout name (potentially in the same second)
    dir2 = stage_and_export_bundle(design2, output_parent_dir=tmp_path, layout_name="COLLISION_HOLO")

    # If timestamps coincided, dir2 gets an incremented suffix; if timestamp ticked, dir2 is a different folder
    # In both cases, dir1 and its contents must be completely intact!
    assert dir1.exists(), "Original bundle directory was deleted!"
    assert marker_file.exists(), "Marker file inside original bundle was destroyed!"
    assert marker_file.read_text(encoding="utf-8") == "preserved_content"

    # If both exports happened in the same second, dir2 is distinct and has _01 suffix
    if dir1.name == dir2.name:
        pytest.fail("Second export returned the exact same directory without collision protection!")

    assert dir2.exists()
    assert (dir2 / "COLLISION_HOLO.gds").exists()
    assert (dir2 / "manifest.json").exists()

    # Verify both bundles have distinct data intact
    art1 = load_design_artifact(dir1 / "design.npz")
    art2 = load_design_artifact(dir2 / "design.npz")
    assert np.all(art1.period_nm == 1000)
    assert np.all(art2.period_nm == 1200)


# ---------------------------------------------------------------------------
# Finding 2: Preserve each legacy preset's default pitch
# ---------------------------------------------------------------------------

def test_legacy_preset_default_pitch_preserved(tmp_path: Path):
    """Verify that CLI and API agree on default pitches (holtida: 20 µm, learning-shaders: 60 µm, unity: 60 µm)."""
    # Create a small test image
    img = np.zeros((4, 4, 3), dtype=np.uint8)
    img[:, :] = [120, 180, 240]
    img_path = tmp_path / "test_legacy.png"
    Image.fromarray(img).save(img_path)

    # 1. holtida-ebl: default 20 µm (20000 nm)
    api_holtida = import_legacy_hls(img_path, preset="holtida-ebl")
    assert api_holtida.pitch_nm == 20000

    out_npz_holtida = tmp_path / "cli_holtida.npz"
    rc = cli_main(["import-legacy", str(img_path), "--preset", "holtida-ebl", "-o", str(out_npz_holtida)])
    assert rc == 0
    cli_holtida = load_design_artifact(out_npz_holtida)
    assert cli_holtida.pitch_nm == 20000

    # 2. learning-shaders: default 60 µm (60000 nm)
    api_ls = import_legacy_hls(img_path, preset="learning-shaders")
    assert api_ls.pitch_nm == 60000

    out_npz_ls = tmp_path / "cli_ls.npz"
    rc = cli_main(["import-legacy", str(img_path), "--preset", "learning-shaders", "-o", str(out_npz_ls)])
    assert rc == 0
    cli_ls = load_design_artifact(out_npz_ls)
    assert cli_ls.pitch_nm == 60000, f"Expected 60000 nm default for learning-shaders, got {cli_ls.pitch_nm}"

    # 3. unity-hsv: default 60 µm (60000 nm)
    api_unity = import_legacy_unity_hsv(img_path)
    assert api_unity.pitch_nm == 60000

    out_npz_unity = tmp_path / "cli_unity.npz"
    rc = cli_main(["import-legacy", str(img_path), "--preset", "unity-hsv", "-o", str(out_npz_unity)])
    assert rc == 0
    cli_unity = load_design_artifact(out_npz_unity)
    assert cli_unity.pitch_nm == 60000, f"Expected 60000 nm default for unity-hsv, got {cli_unity.pitch_nm}"

    # 4. Explicit override works across presets
    out_npz_override = tmp_path / "cli_override.npz"
    rc = cli_main([
        "import-legacy", str(img_path),
        "--preset", "learning-shaders",
        "--pitch-um", "35.5",
        "-o", str(out_npz_override),
    ])
    assert rc == 0
    cli_override = load_design_artifact(out_npz_override)
    assert cli_override.pitch_nm == 35500


# ---------------------------------------------------------------------------
# Finding 3: Evaluate optics at each cell's physical position
# ---------------------------------------------------------------------------

def test_optical_preview_physical_cell_positioning():
    """Verify that full-design optical preview evaluates cells at their centered physical positions."""
    shape = (3, 3)
    period_nm = np.full(shape, 1000, dtype=np.uint32)
    angle_deg = np.zeros(shape, dtype=np.float64)
    active = np.ones(shape, dtype=np.bool_)

    pitch_nm_1 = 20000  # 0.02 mm
    design_1 = Design(shape=shape, pitch_nm=pitch_nm_1, period_nm=period_nm, angle_deg=angle_deg, active=active)
    preview_1 = render_optical_preview(design_1)

    h, w = shape
    pitch_mm_1 = pitch_nm_1 * 1e-6

    # Verify each cell matches independent simulate_cell_optical_color call at that cell's centered position
    for r in range(h):
        for c in range(w):
            x_w = (c + 0.5 - w / 2.0) * pitch_mm_1
            y_w = -(r + 0.5 - h / 2.0) * pitch_mm_1
            expected = simulate_cell_optical_color(1000, 0.0, world_pos=(x_w, y_w, 0.0))
            np.testing.assert_allclose(
                preview_1[r, c],
                expected,
                atol=1e-6,
                err_msg=f"Mismatch at cell ({r}, {c}) for pitch {pitch_nm_1}",
            )

    # Pitch variation test: with a larger pitch (60 µm), coordinates are 3x wider
    pitch_nm_2 = 60000  # 0.06 mm
    design_2 = Design(shape=shape, pitch_nm=pitch_nm_2, period_nm=period_nm, angle_deg=angle_deg, active=active)
    preview_2 = render_optical_preview(design_2)

    # Center cell (1, 1) has (x, y) = (0, 0) in both designs
    np.testing.assert_allclose(preview_1[1, 1], preview_2[1, 1], atol=1e-6)

    # Off-center corner cell (0, 0) has different physical positions (-0.02 mm vs -0.06 mm)
    pitch_mm_2 = pitch_nm_2 * 1e-6
    for r in range(h):
        for c in range(w):
            x_w2 = (c + 0.5 - w / 2.0) * pitch_mm_2
            y_w2 = -(r + 0.5 - h / 2.0) * pitch_mm_2
            expected_2 = simulate_cell_optical_color(1000, 0.0, world_pos=(x_w2, y_w2, 0.0))
            np.testing.assert_allclose(preview_2[r, c], expected_2, atol=1e-6)


# ---------------------------------------------------------------------------
# Finding 4: Round signed angles before adding RGB16 offset
# ---------------------------------------------------------------------------

def test_rgb16_signed_angle_half_step_ties_and_bounds():
    """Verify that RGB16 angle encoding rounds signed angles half-away-from-zero before adding offset."""
    profile = RGB16FixedProfile()

    # Half-step tests: ±0.005° and ±0.015°
    # Under half-away-from-zero on signed angles:
    #   -0.005° * 100 = -0.5  -> rounds to -1.0 -> code = 32767 -> decodes to -0.01°
    #   +0.005° * 100 = +0.5  -> rounds to +1.0 -> code = 32769 -> decodes to +0.01°
    #   -0.015° * 100 = -1.5  -> rounds to -2.0 -> code = 32766 -> decodes to -0.02°
    #   +0.015° * 100 = +1.5  -> rounds to +2.0 -> code = 32770 -> decodes to +0.02°
    test_angles = [-0.005, 0.005, -0.015, 0.015, 0.0]
    expected_dec = [-0.01, 0.01, -0.02, 0.02, 0.0]
    expected_codes = [32767, 32769, 32766, 32770, 32768]

    shape = (1, len(test_angles))
    design = Design(
        shape=shape,
        pitch_nm=20000,
        period_nm=np.full(shape, 1000, dtype=np.uint32),
        angle_deg=np.array([test_angles], dtype=np.float64),
        active=np.ones(shape, dtype=np.bool_),
    )

    encoded, report = profile.encode(design, policy="quantize")
    assert report.verified

    # Verify G channel codes directly
    np.testing.assert_array_equal(encoded[0, :, 1], expected_codes)

    # Decode and verify recovered angles
    decoded = profile.decode(encoded, pitch_nm=20000)
    np.testing.assert_allclose(decoded.angle_deg[0, :], expected_dec, atol=1e-6)

    # Boundary tests: representable range [-327.68°, +327.67°]
    boundary_angles = [-327.68, 327.67]
    boundary_design = Design(
        shape=(1, 2),
        pitch_nm=20000,
        period_nm=np.full((1, 2), 1000, dtype=np.uint32),
        angle_deg=np.array([boundary_angles], dtype=np.float64),
        active=np.ones((1, 2), dtype=np.bool_),
    )
    b_encoded, b_report = profile.encode(boundary_design, policy="reject")
    assert b_report.verified
    assert b_encoded[0, 0, 1] == 0       # code 0 for -327.68°
    assert b_encoded[0, 1, 1] == 65535   # code 65535 for +327.67°

    b_decoded = profile.decode(b_encoded, pitch_nm=20000)
    np.testing.assert_allclose(b_decoded.angle_deg[0, :], boundary_angles, atol=1e-6)

    # Exceeding bounds raises ValueError
    for invalid_angle in [-327.69, 327.68]:
        inv_design = Design(
            shape=(1, 1),
            pitch_nm=20000,
            period_nm=np.full((1, 1), 1000, dtype=np.uint32),
            angle_deg=np.array([[invalid_angle]], dtype=np.float64),
            active=np.ones((1, 1), dtype=np.bool_),
        )
        with pytest.raises(ValueError, match="exceeds 16-bit code range"):
            profile.encode(inv_design, policy="quantize")


# ---------------------------------------------------------------------------
# Finding 5: Convert linear RGB to display sRGB before saving previews
# ---------------------------------------------------------------------------

def test_linear_to_srgb_transfer_function_and_fallback(tmp_path: Path):
    """Verify IEC 61966-2-1 transfer function, breakpoint, and that fallback intensities are not double-converted."""
    # 1. Test linear_to_srgb on known mathematical reference points
    np.testing.assert_allclose(linear_to_srgb(0.0), 0.0, atol=1e-6)
    np.testing.assert_allclose(linear_to_srgb(1.0), 1.0, atol=1e-6)

    # Breakpoint at 0.0031308
    bp = 0.0031308
    val_low = 12.92 * bp
    val_high = 1.055 * (bp ** (1.0 / 2.4)) - 0.055
    np.testing.assert_allclose(linear_to_srgb(bp), val_low, atol=1e-6)
    np.testing.assert_allclose(val_low, val_high, atol=1e-4)

    # Linear 0.25 -> sRGB ~0.5370987 -> byte 137 (not 64)
    srgb_025 = float(linear_to_srgb(0.25))
    np.testing.assert_allclose(srgb_025, 0.5370987, atol=1e-5)
    assert int(round(srgb_025 * 255.0)) == 137

    # 2. Test render_preview_to_file with active diffractive cells vs fallback intensity
    shape = (2, 2)
    # Cell (0, 0) is active; Cell (1, 1) is inactive with fallback_intensity = 0.25
    active = np.zeros(shape, dtype=np.bool_)
    active[0, 0] = True

    fallback = np.full(shape, 0.25, dtype=np.float32)

    design = Design(
        shape=shape,
        pitch_nm=20000,
        period_nm=np.full(shape, 1000, dtype=np.uint32),
        angle_deg=np.zeros(shape, dtype=np.float64),
        active=active,
        fallback_intensity=fallback,
    )

    out_png = tmp_path / "preview_corrected.png"
    render_preview_to_file(design, out_png, preset="corrected")
    assert out_png.exists()

    with Image.open(out_png) as im:
        arr = np.array(im)

    # Inactive cell (1, 1) has fallback_intensity 0.25.
    # Fallback intensity is ALREADY in display sRGB and MUST NOT be double-converted!
    # Direct uint8 of 0.25 is round(0.25 * 255) == 64.
    # If it were erroneously double-converted, it would be 137.
    assert arr[1, 1, 0] == 64, f"Fallback intensity was double-converted! Expected 64, got {arr[1, 1, 0]}"
    assert arr[1, 1, 1] == 64
    assert arr[1, 1, 2] == 64

    # Legacy preset ("glsl-legacy"): writes direct ungamma-corrected output
    out_legacy_png = tmp_path / "preview_legacy.png"
    render_preview_to_file(design, out_legacy_png, preset="glsl-legacy")
    assert out_legacy_png.exists()
