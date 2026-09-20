"""Staged atomic multi-file export bundle and manifest generation."""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.io.artifacts import save_design_artifact
from dot_ebl_preview.io.text_exports import export_text_parameters
from dot_ebl_preview.jobs.progress import ProgressTracker
from dot_ebl_preview.layout.plan import FabricationPlan, create_fabrication_plan


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def stage_and_export_bundle(
    design: Design,
    output_parent_dir: Union[str, Path],
    layout_name: str = "HOLOGRAM",
    tracker: Optional[ProgressTracker] = None,
    interruption_stage: Optional[int] = None,
    render_angles: Optional[Sequence[float]] = (0.0, 45.0, 90.0, 135.0),
    preview_preset: str = "corrected",
) -> Path:
    """Stage and publish complete EBL export bundle atomically.

    Bundle includes:
      - {layout_name}.gds
      - angles.txt
      - gratings.txt
      - design.npz
      - manifest.json

    If interruption_stage is set, raises an exception after stage N for testing recovery.
    """
    parent = Path(output_parent_dir)
    parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    final_dir_base = f"{timestamp}_{layout_name}"

    # Stage inside a uniquely allocated temporary directory on the same filesystem
    staging_id = uuid.uuid4().hex
    temp_dir = parent / f".tmp_{timestamp}_{layout_name}_{staging_id}"
    temp_dir.mkdir(parents=True, exist_ok=False)

    if tracker is not None:
        tracker.update_to(0)

    try:
        # Step 1: Create fabrication plan
        plan: FabricationPlan = create_fabrication_plan(design, top_name=layout_name)
        if tracker is not None:
            tracker.advance(1)
        if interruption_stage == 1:
            raise RuntimeError("Interrupted at stage 1")

        # Step 2: Write GDSII
        gds_path = temp_dir / f"{layout_name}.gds"
        plan.library.write_gds(gds_path)
        if tracker is not None:
            tracker.advance(1)
        if interruption_stage == 2:
            raise RuntimeError("Interrupted at stage 2")

        # Step 3: Export text parameter maps
        angles_path, gratings_path = export_text_parameters(temp_dir, design)
        if tracker is not None:
            tracker.advance(1)
        if interruption_stage == 3:
            raise RuntimeError("Interrupted at stage 3")

        # Step 4: Save canonical design.npz
        npz_path = temp_dir / "design.npz"
        save_design_artifact(npz_path, design)
        if tracker is not None:
            tracker.advance(1)
        if interruption_stage == 4:
            raise RuntimeError("Interrupted at stage 4")

        # Step 4.5: Render multi-angle optical previews if specified
        preview_files: List[Path] = []
        if render_angles:
            from dot_ebl_preview.preview.renderer import render_angle_previews_to_directory

            preview_files = render_angle_previews_to_directory(
                design,
                output_dir=temp_dir,
                angles_deg=render_angles,
                preset=preview_preset,
            )

        # Step 5: Verify all staged files and build manifest
        files_to_manifest = [gds_path, angles_path, gratings_path, npz_path] + preview_files
        manifest_files: Dict[str, Dict[str, Any]] = {}

        for f in files_to_manifest:
            if not f.exists():
                raise FileNotFoundError(f"Expected staged file missing: {f}")
            manifest_files[f.name] = {
                "size_bytes": f.stat().st_size,
                "sha256": _file_sha256(f),
            }

        manifest_data = {
            "version": "1.0",
            "timestamp": timestamp,
            "layout_name": layout_name,
            "design_hash": design.content_hash(),
            "plan_hash": plan.plan_hash,
            "total_cells": plan.total_cells,
            "active_cells": plan.active_cells,
            "total_stripes": plan.total_stripes,
            "skipped_degenerate_stripes": plan.skipped_degenerate_stripes,
            "unique_periods_count": plan.unique_periods_count,
            "files": manifest_files,
            "status": "COMPLETED",
        }

        manifest_path = temp_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest_data, mf, indent=2)

        if tracker is not None:
            tracker.advance(1)
        if interruption_stage == 5:
            raise RuntimeError("Interrupted at stage 5")

        # Step 6: Safe atomic publish rename avoiding collisions and preserving existing bundles
        counter = 0
        final_dir = parent / final_dir_base
        while True:
            candidate = parent / (final_dir_base if counter == 0 else f"{final_dir_base}_{counter:02d}")
            if not candidate.exists():
                try:
                    temp_dir.rename(candidate)
                    final_dir = candidate
                    break
                except (FileExistsError, OSError):
                    # Handled if another process/thread claimed candidate concurrently
                    pass
            counter += 1

        if tracker is not None:
            tracker.finish()

        return final_dir

    except Exception:
        # Clean up temporary directory on failure or cancellation
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
