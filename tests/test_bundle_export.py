"""Tests for atomic multi-file bundle staging, manifest, and interruption recovery (Critic Review R5)."""

import json
from pathlib import Path
import numpy as np
import pytest

from dot_ebl_preview.api import dot_matrix_hologram, export_bundle
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.jobs.bundle import stage_and_export_bundle


def test_atomic_bundle_export_success(tmp_path: Path):
    shape = (2, 2)
    period_nm = np.array([[900, 1000], [1100, 1200]], dtype=np.uint32)
    angle_deg = np.array([[0.0, 45.0], [-45.0, 90.0]], dtype=np.float64)
    active = np.array([[True, True], [True, True]], dtype=np.bool_)

    design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)

    out_bundle_dir = stage_and_export_bundle(design, output_parent_dir=tmp_path, layout_name="TEST_HOLO")
    assert out_bundle_dir.exists()

    # Check that all expected files exist
    assert (out_bundle_dir / "TEST_HOLO.gds").exists()
    assert (out_bundle_dir / "angles.txt").exists()
    assert (out_bundle_dir / "gratings.txt").exists()
    assert (out_bundle_dir / "design.npz").exists()
    assert (out_bundle_dir / "manifest.json").exists()

    # Verify manifest
    with open(out_bundle_dir / "manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["status"] == "COMPLETED"
    assert manifest["active_cells"] == 4
    assert "TEST_HOLO.gds" in manifest["files"]
    assert "angles.txt" in manifest["files"]
    assert "gratings.txt" in manifest["files"]
    assert "design.npz" in manifest["files"]


def test_bundle_interruption_leaves_no_partial_artifacts(tmp_path: Path):
    """Critic Review R5: Interruption before completion leaves no partial published output."""
    shape = (2, 2)
    design = Design(
        shape=shape,
        pitch_nm=20000,
        period_nm=np.full(shape, 1000, dtype=np.uint32),
        angle_deg=np.zeros(shape, dtype=np.float64),
        active=np.ones(shape, dtype=np.bool_),
    )

    # Simulate failure at stage 3 (after text export, before npz)
    with pytest.raises(RuntimeError, match="Interrupted at stage 3"):
        stage_and_export_bundle(
            design,
            output_parent_dir=tmp_path,
            layout_name="FAIL_HOLO",
            interruption_stage=3,
        )

    # Verify that no directory starting with FAIL_HOLO or published output was created
    subdirs = list(tmp_path.iterdir())
    assert len(subdirs) == 0, f"Expected clean directory after interruption, but found: {subdirs}"


def test_dot_matrix_hologram_wrapper(tmp_path: Path):
    from PIL import Image

    # Create dummy BMP image
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    img[:, :] = [100, 150, 200]
    img_file = tmp_path / "test.bmp"
    Image.fromarray(img).save(img_file)

    # write=False should return None and create no output files
    out_dir = tmp_path / "output_test"
    plan_none = dot_matrix_hologram(
        name="NO_WRITE",
        image=str(img_file),
        write=False,
        output_dir=out_dir,
    )
    assert plan_none is None
    assert not out_dir.exists()

    # write=True should return FabricationPlan and create output
    plan_write = dot_matrix_hologram(
        name="DO_WRITE",
        image=str(img_file),
        write=True,
        output_dir=out_dir,
    )
    assert plan_write is not None
    assert out_dir.exists()
