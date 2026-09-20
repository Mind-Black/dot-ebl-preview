"""Comprehensive tests for the dot-ebl command line interface (tests/test_cli.py)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import pytest

from dot_ebl_preview.cli import main
from dot_ebl_preview.core.encoding import RGB8IndexedProfile, RGB16FixedProfile
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.io.artifacts import load_design_artifact, save_design_artifact


@pytest.fixture
def sample_design_npz(tmp_path: Path) -> Path:
    """Create a sample 2x2 valid Design and save it to an .npz file."""
    shape = (2, 2)
    period_nm = np.array([[900, 1000], [1100, 1200]], dtype=np.uint32)
    angle_deg = np.array([[0.0, 45.0], [-45.0, 90.0]], dtype=np.float64)
    active = np.array([[True, True], [True, False]], dtype=np.bool_)

    design = Design(
        shape=shape,
        pitch_nm=20000,
        period_nm=period_nm,
        angle_deg=angle_deg,
        active=active,
        source_identity="test_cli_fixture",
    )
    npz_path = tmp_path / "sample_design.npz"
    save_design_artifact(npz_path, design)
    return npz_path


@pytest.fixture
def empty_design_npz(tmp_path: Path) -> Path:
    """Create an empty (all inactive cells) Design and save it to an .npz file."""
    shape = (3, 3)
    period_nm = np.zeros(shape, dtype=np.uint32)
    angle_deg = np.zeros(shape, dtype=np.float64)
    active = np.zeros(shape, dtype=np.bool_)

    design = Design(
        shape=shape,
        pitch_nm=20000,
        period_nm=period_nm,
        angle_deg=angle_deg,
        active=active,
        source_identity="empty_cli_fixture",
    )
    npz_path = tmp_path / "empty_design.npz"
    save_design_artifact(npz_path, design)
    return npz_path


@pytest.fixture
def single_pixel_design_npz(tmp_path: Path) -> Path:
    """Create a 1x1 single pixel active Design and save it to an .npz file."""
    shape = (1, 1)
    period_nm = np.array([[1000]], dtype=np.uint32)
    angle_deg = np.array([[30.0]], dtype=np.float64)
    active = np.array([[True]], dtype=np.bool_)

    design = Design(
        shape=shape,
        pitch_nm=20000,
        period_nm=period_nm,
        angle_deg=angle_deg,
        active=active,
        source_identity="single_pixel_fixture",
    )
    npz_path = tmp_path / "single_pixel.npz"
    save_design_artifact(npz_path, design)
    return npz_path


@pytest.fixture
def sample_rgb8_image(tmp_path: Path) -> Path:
    """Create an encoded uint8 RGB parameter image matching RGB8IndexedProfile."""
    # R=0 (900 nm), G=90 (0 deg), B=255 (active)
    # R=10 (1000 nm), G=135 (45 deg), B=0 (inactive)
    img_data = np.zeros((2, 2, 3), dtype=np.uint8)
    img_data[0, 0] = [0, 90, 255]
    img_data[0, 1] = [10, 135, 255]
    img_data[1, 0] = [20, 45, 255]
    img_data[1, 1] = [0, 0, 0]  # Inactive

    img_path = tmp_path / "param_rgb8.png"
    Image.fromarray(img_data, mode="RGB").save(img_path)
    return img_path


@pytest.fixture
def legacy_color_image(tmp_path: Path) -> Path:
    """Create a legacy RGB test image with color pixels and background."""
    img_data = np.zeros((8, 8, 3), dtype=np.uint8)
    # Fill background with black (val=0 -> inactive)
    # Put some colored pixels in center
    img_data[2:6, 2:6] = [200, 100, 50]
    img_path = tmp_path / "legacy_test.png"
    Image.fromarray(img_data, mode="RGB").save(img_path)
    return img_path


# =========================================================================
# Top-level CLI behaviors and error handling
# =========================================================================

def test_cli_no_arguments(capsys: pytest.CaptureFixture[str]):
    """Invoking dot-ebl without subcommands must raise SystemExit (exit code 2)."""
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "usage:" in captured.err or "usage:" in captured.out


def test_cli_top_level_help(capsys: pytest.CaptureFixture[str]):
    """Invoking dot-ebl --help must exit cleanly with code 0 and show help."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Combined hologram optical preview and Raith EBL layout application" in captured.out
    assert "inspect" in captured.out
    assert "import-legacy" in captured.out
    assert "export" in captured.out
    assert "preview" in captured.out


def test_cli_unknown_command():
    """Invoking an invalid subcommand must raise SystemExit with code 2."""
    with pytest.raises(SystemExit) as exc_info:
        main(["nonexistent-subcommand"])
    assert exc_info.value.code == 2


def test_cli_subprocess_entrypoint():
    """Verify python -m dot_ebl_preview.cli can be invoked as an entry point."""
    cmd = [sys.executable, "-m", "dot_ebl_preview.cli", "--help"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    assert "dot-ebl" in result.stdout or "usage:" in result.stdout


# =========================================================================
# Inspect command tests
# =========================================================================

def test_cli_inspect_help(capsys: pytest.CaptureFixture[str]):
    """Inspect --help exits with 0 and explains arguments."""
    with pytest.raises(SystemExit) as exc_info:
        main(["inspect", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--profile" in captured.out
    assert "--pitch-um" in captured.out


def test_cli_inspect_npz_success(sample_design_npz: Path, capsys: pytest.CaptureFixture[str]):
    """Inspect on valid .npz outputs complete JSON metadata."""
    ret = main(["inspect", str(sample_design_npz)])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["shape"] == [2, 2]
    assert data["pitch_nm"] == 20000
    assert data["pitch_um"] == 20.0
    assert data["total_cells"] == 4
    assert data["active_cells"] == 3
    assert data["active_percentage"] == 75.0
    assert "extents_um" in data
    assert data["extents_um"]["x_min"] == 0.0
    assert data["extents_um"]["x_max"] == 40.0
    assert data["extents_um"]["y_min"] == -40.0
    assert data["extents_um"]["y_max"] == 0.0
    assert "content_hash" in data
    assert len(data["content_hash"]) == 64


def test_cli_inspect_rgb8_image(sample_rgb8_image: Path, capsys: pytest.CaptureFixture[str]):
    """Inspect on RGB8 image using default profile."""
    ret = main(["inspect", str(sample_rgb8_image)])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["shape"] == [2, 2]
    assert data["active_cells"] == 3
    assert data["total_cells"] == 4


def test_cli_inspect_custom_pitch(sample_rgb8_image: Path, capsys: pytest.CaptureFixture[str]):
    """Inspect with --pitch-um 25.5 converts correctly to pitch_nm 25500."""
    ret = main(["inspect", str(sample_rgb8_image), "--pitch-um", "25.5"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["pitch_nm"] == 25500
    assert data["pitch_um"] == 25.5


def test_cli_inspect_empty_design(empty_design_npz: Path, capsys: pytest.CaptureFixture[str]):
    """Inspect on a zero-active design handles empty statistics gracefully."""
    ret = main(["inspect", str(empty_design_npz)])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["active_cells"] == 0
    assert data["active_percentage"] == 0.0
    assert data["unique_periods_nm"] == []
    assert data["unique_angles_deg"] == []
    assert data["total_stripes"] == 0


def test_cli_inspect_single_pixel(single_pixel_design_npz: Path, capsys: pytest.CaptureFixture[str]):
    """Inspect on a 1x1 design outputs 1 cell."""
    ret = main(["inspect", str(single_pixel_design_npz)])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["shape"] == [1, 1]
    assert data["total_cells"] == 1
    assert data["active_cells"] == 1
    assert data["active_percentage"] == 100.0


def test_cli_inspect_missing_file():
    """Inspect on a non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        main(["inspect", "non_existent_design_path_12345.npz"])


def test_cli_inspect_invalid_profile(sample_rgb8_image: Path):
    """Inspect with an invalid profile raises SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        main(["inspect", str(sample_rgb8_image), "--profile", "unsupported-profile"])
    assert exc_info.value.code == 2


# =========================================================================
# Import-legacy command tests
# =========================================================================

def test_cli_import_legacy_help(capsys: pytest.CaptureFixture[str]):
    """Import-legacy --help shows options."""
    with pytest.raises(SystemExit) as exc_info:
        main(["import-legacy", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--preset" in captured.out
    assert "--mode" in captured.out
    assert "--downscale" in captured.out
    assert "--filter" in captured.out


def test_cli_import_legacy_default(legacy_color_image: Path, tmp_path: Path):
    """Import-legacy with default parameters produces a valid design.npz."""
    out_npz = tmp_path / "imported_holtida.npz"
    ret = main(["import-legacy", str(legacy_color_image), "-o", str(out_npz)])
    assert ret == 0
    assert out_npz.exists()

    design = load_design_artifact(out_npz)
    assert design.shape == (8, 8)
    assert design.pitch_nm == 20000
    assert design.active_count > 0


def test_cli_import_legacy_exact_mode(legacy_color_image: Path, tmp_path: Path):
    """Import-legacy with --mode legacy-exact."""
    out_npz = tmp_path / "imported_exact.npz"
    ret = main(["import-legacy", str(legacy_color_image), "--mode", "legacy-exact", "-o", str(out_npz)])
    assert ret == 0
    assert out_npz.exists()

    design = load_design_artifact(out_npz)
    assert design.shape == (8, 8)


def test_cli_import_legacy_learning_shaders_preset(legacy_color_image: Path, tmp_path: Path):
    """Import-legacy with --preset learning-shaders uses 60 µm default pitch."""
    out_npz = tmp_path / "imported_ls.npz"
    ret = main(["import-legacy", str(legacy_color_image), "--preset", "learning-shaders", "-o", str(out_npz)])
    assert ret == 0
    assert out_npz.exists()

    design = load_design_artifact(out_npz)
    # Default pitch for learning-shaders without --pitch-um override in cli is 20000 because cli defaults pitch-um=20.0
    assert design.shape == (8, 8)


def test_cli_import_legacy_unity_hsv_preset(legacy_color_image: Path, tmp_path: Path):
    """Import-legacy with --preset unity-hsv."""
    out_npz = tmp_path / "imported_unity.npz"
    ret = main(["import-legacy", str(legacy_color_image), "--preset", "unity-hsv", "-o", str(out_npz)])
    assert ret == 0
    assert out_npz.exists()

    design = load_design_artifact(out_npz)
    assert design.shape == (8, 8)
    assert design.fallback_intensity is not None


def test_cli_import_legacy_downscale(legacy_color_image: Path, tmp_path: Path):
    """Import-legacy with --downscale 2 halves spatial dimensions."""
    out_npz = tmp_path / "downscaled.npz"
    ret = main(["import-legacy", str(legacy_color_image), "--downscale", "2", "-o", str(out_npz)])
    assert ret == 0
    assert out_npz.exists()

    design = load_design_artifact(out_npz)
    assert design.shape == (4, 4)
    # Check that operation was recorded in audit log
    op_names = [op.name for op in design.operations]
    assert "downscale" in op_names


def test_cli_import_legacy_gaussian_filter(legacy_color_image: Path, tmp_path: Path):
    """Import-legacy with --filter gaussian applies gaussian smoothing."""
    out_npz = tmp_path / "filtered_gaussian.npz"
    ret = main(["import-legacy", str(legacy_color_image), "--filter", "gaussian", "-o", str(out_npz)])
    assert ret == 0
    assert out_npz.exists()

    design = load_design_artifact(out_npz)
    op_names = [op.name for op in design.operations]
    assert "apply_gaussian_filter" in op_names


def test_cli_import_legacy_bilateral_filter(legacy_color_image: Path, tmp_path: Path):
    """Import-legacy with --filter bilateral applies bilateral filter."""
    out_npz = tmp_path / "filtered_bilateral.npz"
    ret = main(["import-legacy", str(legacy_color_image), "--filter", "bilateral", "-o", str(out_npz)])
    assert ret == 0
    assert out_npz.exists()

    design = load_design_artifact(out_npz)
    op_names = [op.name for op in design.operations]
    assert "apply_bilateral_filter" in op_names


def test_cli_import_legacy_missing_output(legacy_color_image: Path):
    """Missing required -o/--output flag must raise SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        main(["import-legacy", str(legacy_color_image)])
    assert exc_info.value.code == 2


def test_cli_import_legacy_invalid_filter(legacy_color_image: Path, tmp_path: Path):
    """Invalid filter option raises SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        main(["import-legacy", str(legacy_color_image), "--filter", "box", "-o", str(tmp_path / "out.npz")])
    assert exc_info.value.code == 2


# =========================================================================
# Export command tests
# =========================================================================

def test_cli_export_help(capsys: pytest.CaptureFixture[str]):
    """Export --help shows bundle options."""
    with pytest.raises(SystemExit) as exc_info:
        main(["export", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--name" in captured.out
    assert "--output-dir" in captured.out
    assert "--profile" in captured.out


def test_cli_export_from_npz(sample_design_npz: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Export bundle from .npz design file."""
    out_parent = tmp_path / "export_bundles"
    ret = main(["export", str(sample_design_npz), "--name", "TEST_CLI_HOLO", "-o", str(out_parent)])
    assert ret == 0

    # Locate generated timestamped folder
    created_dirs = list(out_parent.glob("*_TEST_CLI_HOLO"))
    assert len(created_dirs) == 1
    bundle_dir = created_dirs[0]

    # Verify all expected artifacts exist in bundle
    assert (bundle_dir / "TEST_CLI_HOLO.gds").exists()
    assert (bundle_dir / "angles.txt").exists()
    assert (bundle_dir / "gratings.txt").exists()
    assert (bundle_dir / "design.npz").exists()
    assert (bundle_dir / "manifest.json").exists()

    with open(bundle_dir / "manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["status"] == "COMPLETED"
    assert manifest["layout_name"] == "TEST_CLI_HOLO"
    assert manifest["active_cells"] == 3


def test_cli_export_from_image(sample_rgb8_image: Path, tmp_path: Path):
    """Export bundle directly from an RGB8 parameter image."""
    out_parent = tmp_path / "export_from_img"
    ret = main(["export", str(sample_rgb8_image), "--name", "IMAGE_HOLO", "-o", str(out_parent)])
    assert ret == 0

    created_dirs = list(out_parent.glob("*_IMAGE_HOLO"))
    assert len(created_dirs) == 1
    bundle_dir = created_dirs[0]
    assert (bundle_dir / "IMAGE_HOLO.gds").exists()
    assert (bundle_dir / "manifest.json").exists()


def test_cli_export_empty_design(empty_design_npz: Path, tmp_path: Path):
    """Export bundle on a zero-active design creates valid empty bundle."""
    out_parent = tmp_path / "export_empty"
    ret = main(["export", str(empty_design_npz), "--name", "EMPTY_HOLO", "-o", str(out_parent)])
    assert ret == 0

    created_dirs = list(out_parent.glob("*_EMPTY_HOLO"))
    assert len(created_dirs) == 1
    bundle_dir = created_dirs[0]
    assert (bundle_dir / "EMPTY_HOLO.gds").exists()

    with open(bundle_dir / "manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["active_cells"] == 0
    assert manifest["total_stripes"] == 0


def test_cli_export_single_pixel(single_pixel_design_npz: Path, tmp_path: Path):
    """Export bundle on a 1x1 design."""
    out_parent = tmp_path / "export_single_px"
    ret = main(["export", str(single_pixel_design_npz), "--name", "SINGLE_PX", "-o", str(out_parent)])
    assert ret == 0

    created_dirs = list(out_parent.glob("*_SINGLE_PX"))
    assert len(created_dirs) == 1
    bundle_dir = created_dirs[0]
    assert (bundle_dir / "SINGLE_PX.gds").exists()


def test_cli_export_missing_file():
    """Export on non-existent input raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        main(["export", "missing_file_xyz.npz"])


# =========================================================================
# Preview command tests
# =========================================================================

def test_cli_preview_help(capsys: pytest.CaptureFixture[str]):
    """Preview --help shows options."""
    with pytest.raises(SystemExit) as exc_info:
        main(["preview", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--output" in captured.out
    assert "--preset" in captured.out


def test_cli_preview_from_npz(sample_design_npz: Path, tmp_path: Path):
    """Render preview from .npz design to PNG."""
    out_png = tmp_path / "preview.png"
    ret = main(["preview", str(sample_design_npz), "-o", str(out_png)])
    assert ret == 0
    assert out_png.exists()

    with Image.open(out_png) as im:
        assert im.size == (2, 2)
        assert im.mode == "RGB"


def test_cli_preview_from_image(sample_rgb8_image: Path, tmp_path: Path):
    """Render preview from RGB parameter image."""
    out_png = tmp_path / "preview_from_img.png"
    ret = main(["preview", str(sample_rgb8_image), "-o", str(out_png)])
    assert ret == 0
    assert out_png.exists()


@pytest.mark.parametrize("preset", ["corrected", "glsl-legacy", "unity-hsv"])
def test_cli_preview_presets(sample_design_npz: Path, tmp_path: Path, preset: str):
    """Render preview using all supported optical presets."""
    out_png = tmp_path / f"preview_{preset}.png"
    ret = main(["preview", str(sample_design_npz), "-o", str(out_png), "--preset", preset])
    assert ret == 0
    assert out_png.exists()
    assert out_png.stat().st_size > 0


def test_cli_preview_empty_design(empty_design_npz: Path, tmp_path: Path):
    """Render preview on a zero-active design produces valid all-black image."""
    out_png = tmp_path / "preview_empty.png"
    ret = main(["preview", str(empty_design_npz), "-o", str(out_png)])
    assert ret == 0
    assert out_png.exists()

    with Image.open(out_png) as im:
        arr = np.array(im)
        assert np.all(arr == 0)


def test_cli_preview_single_pixel(single_pixel_design_npz: Path, tmp_path: Path):
    """Render preview on 1x1 design produces a 1x1 image."""
    out_png = tmp_path / "preview_single.png"
    ret = main(["preview", str(single_pixel_design_npz), "-o", str(out_png)])
    assert ret == 0
    assert out_png.exists()

    with Image.open(out_png) as im:
        assert im.size == (1, 1)


def test_cli_preview_missing_output(sample_design_npz: Path):
    """Preview missing required -o/--output raises SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        main(["preview", str(sample_design_npz)])
    assert exc_info.value.code == 2


def test_cli_preview_invalid_preset(sample_design_npz: Path, tmp_path: Path):
    """Preview with invalid preset raises SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        main(["preview", str(sample_design_npz), "-o", str(tmp_path / "out.png"), "--preset", "unsupported"])
    assert exc_info.value.code == 2


def test_cli_preview_missing_input_file(tmp_path: Path):
    """Preview on non-existent input file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        main(["preview", "missing_preview_input.npz", "-o", str(tmp_path / "out.png")])


# =========================================================================
# Additional CLI edge cases: format errors, invalid types, profile mismatch
# =========================================================================

def test_cli_inspect_jpeg_prohibited(tmp_path: Path):
    """Parameter images in JPEG format must be rejected."""
    jpg_path = tmp_path / "test.jpg"
    jpg_path.write_bytes(b"dummy jpeg content")
    with pytest.raises(ValueError, match="JPEG format is prohibited"):
        main(["inspect", str(jpg_path)])


def test_cli_export_jpeg_prohibited(tmp_path: Path):
    """Export bundle with JPEG input must be rejected."""
    jpg_path = tmp_path / "test.jpeg"
    jpg_path.write_bytes(b"dummy jpeg content")
    with pytest.raises(ValueError, match="JPEG format is prohibited"):
        main(["export", str(jpg_path)])


def test_cli_inspect_rgb16_on_uint8_image_error(sample_rgb8_image: Path):
    """Using rgb16 profile on uint8 image must raise ValueError."""
    with pytest.raises(ValueError, match="requires uint16 image"):
        main(["inspect", str(sample_rgb8_image), "--profile", "rgb16-fixed-v1"])


def test_cli_export_rgb16_on_uint8_image_error(sample_rgb8_image: Path, tmp_path: Path):
    """Exporting with rgb16 profile on uint8 image must raise ValueError."""
    with pytest.raises(ValueError, match="requires uint16 image"):
        main(["export", str(sample_rgb8_image), "--profile", "rgb16-fixed-v1", "-o", str(tmp_path)])


def test_cli_invalid_pitch_type(sample_rgb8_image: Path):
    """Non-numeric pitch parameter raises SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        main(["inspect", str(sample_rgb8_image), "--pitch-um", "not_a_number"])
    assert exc_info.value.code == 2


def test_cli_invalid_downscale_type(legacy_color_image: Path, tmp_path: Path):
    """Non-integer downscale parameter raises SystemExit."""
    with pytest.raises(SystemExit) as exc_info:
        main(["import-legacy", str(legacy_color_image), "--downscale", "not_an_int", "-o", str(tmp_path / "out.npz")])
    assert exc_info.value.code == 2


def test_cli_import_legacy_custom_pitch(legacy_color_image: Path, tmp_path: Path):
    """Import-legacy with custom --pitch-um 32.5 correctly stores pitch_nm 32500."""
    out_npz = tmp_path / "custom_pitch.npz"
    ret = main(["import-legacy", str(legacy_color_image), "--pitch-um", "32.5", "-o", str(out_npz)])
    assert ret == 0
    assert out_npz.exists()

    design = load_design_artifact(out_npz)
    assert design.pitch_nm == 32500


def test_cli_export_custom_pitch_from_image(sample_rgb8_image: Path, tmp_path: Path):
    """Export from image with custom --pitch-um 15.0."""
    out_parent = tmp_path / "custom_pitch_export"
    ret = main(["export", str(sample_rgb8_image), "--pitch-um", "15.0", "-o", str(out_parent)])
    assert ret == 0

    bundle_dirs = list(out_parent.glob("*_HOLOGRAM"))
    assert len(bundle_dirs) == 1
    design = load_design_artifact(bundle_dirs[0] / "design.npz")
    assert design.pitch_nm == 15000

