"""End-to-end integration tests for whole process functionality with test.png."""

import json
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import pytest

from dot_ebl_preview.api import build_design, build_layout, export_bundle, inspect_design
from dot_ebl_preview.jobs.bundle import stage_and_export_bundle
from dot_ebl_preview.preview.renderer import render_angle_previews_to_directory


def test_test_hologram_file_exists():
    """Verify test.png is present in _INPUT and root workspace."""
    p_input = Path("_INPUT/test.png")
    p_root = Path("test.png")
    assert p_input.exists(), f"Expected {p_input} to exist"
    assert p_root.exists(), f"Expected {p_root} to exist"

    im = Image.open(p_input)
    assert im.size == (128, 128)
    assert im.mode == "RGB"


def test_test_png_decoding_and_inspection():
    """Verify test.png decodes with full spectrum periods and diverse angles."""
    design = build_design("test.png", encoding_profile="rgb8-indexed-v1", pitch_nm=20000)
    info = inspect_design(design)

    assert design.shape == (128, 128)
    assert design.pitch_nm == 20000
    assert info["active_cells"] == 9845
    assert info["total_cells"] == 16384
    assert 55.0 < info["active_percentage"] < 65.0

    # Verify multi-period spectral coverage (900 nm to 1200 nm)
    expected_periods = [900, 950, 980, 1000, 1050, 1100, 1150, 1200]
    assert sorted(info["unique_periods_nm"]) == expected_periods

    # Verify multi-angle orientation coverage (-90 deg to +90 deg)
    expected_angles = [-90.0, -60.0, -45.0, -30.0, 0.0, 30.0, 45.0, 90.0]
    assert sorted(info["unique_angles_deg"]) == expected_angles


def test_test_png_layout_plan():
    """Verify fabrication layout compilation on test.png."""
    design = build_design("test.png", encoding_profile="rgb8-indexed-v1", pitch_nm=20000)
    plan = build_layout(design, top_name="TEST_E2E")

    assert plan.total_cells == 16384
    assert plan.active_cells == 9845
    assert plan.total_stripes == 154
    assert plan.skipped_degenerate_stripes == 0
    assert plan.unique_periods_count == 8
    assert len(plan.library.structures) == 9  # 8 period cells + top cell


def test_whole_process_bundle_export_with_multi_angle_previews(tmp_path: Path):
    """Verify bundle export outputs GDS, texts, NPZ, manifest, and multi-angle previews."""
    design = build_design("test.png", encoding_profile="rgb8-indexed-v1", pitch_nm=20000)
    angles = [0.0, 45.0, 90.0, 135.0]

    bundle_dir = stage_and_export_bundle(
        design,
        output_parent_dir=tmp_path,
        layout_name="E2E_HOLO",
        render_angles=angles,
        preview_preset="corrected",
    )
    assert bundle_dir.exists()

    # Verify standard fabrication files
    assert (bundle_dir / "E2E_HOLO.gds").exists()
    assert (bundle_dir / "angles.txt").exists()
    assert (bundle_dir / "gratings.txt").exists()
    assert (bundle_dir / "design.npz").exists()
    assert (bundle_dir / "manifest.json").exists()

    # Verify multi-angle preview images in the output folder
    assert (bundle_dir / "preview.png").exists()
    assert (bundle_dir / "preview_angle_az0.png").exists()
    assert (bundle_dir / "preview_angle_az45.png").exists()
    assert (bundle_dir / "preview_angle_az90.png").exists()
    assert (bundle_dir / "preview_angle_az135.png").exists()

    # Verify image properties and that different angles produce distinct diffractive appearances
    img0 = np.array(Image.open(bundle_dir / "preview_angle_az0.png"))
    img45 = np.array(Image.open(bundle_dir / "preview_angle_az45.png"))
    img90 = np.array(Image.open(bundle_dir / "preview_angle_az90.png"))
    img135 = np.array(Image.open(bundle_dir / "preview_angle_az135.png"))

    assert img0.shape == (128, 128, 3)
    assert img45.shape == (128, 128, 3)
    assert img90.shape == (128, 128, 3)
    assert img135.shape == (128, 128, 3)

    # Previews at different angles must not be identical
    assert not np.array_equal(img0, img45)
    assert not np.array_equal(img0, img90)
    assert not np.array_equal(img45, img90)
    assert not np.array_equal(img45, img135)

    # Inactive cells (outside the circle) must remain black across all angles
    inactive_mask = ~design.active
    assert np.all(img0[inactive_mask] == 0)
    assert np.all(img45[inactive_mask] == 0)
    assert np.all(img90[inactive_mask] == 0)
    assert np.all(img135[inactive_mask] == 0)

    # Active cells must contain diffracted spectral colors
    assert np.sum(img0[design.active]) > 0
    assert np.sum(img45[design.active]) > 0
    assert np.sum(img90[design.active]) > 0
    assert np.sum(img135[design.active]) > 0

    # Verify manifest.json integrity
    with open(bundle_dir / "manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["status"] == "COMPLETED"
    files = manifest["files"]
    expected_files = [
        "E2E_HOLO.gds",
        "angles.txt",
        "gratings.txt",
        "design.npz",
        "preview.png",
        "preview_angle_az0.png",
        "preview_angle_az45.png",
        "preview_angle_az90.png",
        "preview_angle_az135.png",
    ]
    for ef in expected_files:
        assert ef in files, f"Missing file in manifest: {ef}"
        assert files[ef]["size_bytes"] > 0
        assert len(files[ef]["sha256"]) == 64


def test_run_test_script_execution():
    """Verify run_test.py script executes successfully via subprocess."""
    proc = subprocess.run(
        [sys.executable, "run_test.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"run_test.py failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "ALL CHECKS PASSED: Full process functionality verified." in proc.stdout
    assert "preview_angle_az0.png" in proc.stdout
    assert "preview_angle_az45.png" in proc.stdout
    assert "preview_angle_az90.png" in proc.stdout
    assert "preview_angle_az135.png" in proc.stdout
