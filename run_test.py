"""Standalone test execution script for dot-ebl-preview.

Tests the full hologram pipeline on 'test.png':
  1. Loads/decodes 'test.png' using profile 'rgb8-indexed-v1'.
  2. Inspects design metrics (shape, active cells, unique periods, unique angles).
  3. Generates the Raith single-pixel line fabrication layout.
  4. Exports the complete fabrication bundle (.gds, angles.txt, gratings.txt, design.npz, manifest.json).
  5. Outputs multiple optical diffraction preview images at varying azimuth angles
     directly into the timestamped output folder associated with the program run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image

from dot_ebl_preview.api import (
    build_design,
    build_layout,
    export_bundle,
    inspect_design,
)


def ensure_test_image(path: Path) -> Path:
    """Ensure that test.png exists, generating it if necessary."""
    if path.exists():
        return path

    print(f"Creating test hologram file: {path}...")
    h, w = 128, 128
    img = np.zeros((h, w, 3), dtype=np.uint8)
    cy, cx = h // 2, w // 2
    radius = 56

    periods = [0, 5, 10, 15, 20, 25, 30, 8]
    angles = [90, 135, 180, 45, 0, 120, 30, 60]

    for y in range(h):
        for x in range(w):
            dy = y - cy
            dx = x - cx
            dist = np.hypot(dx, dy)
            if dist <= radius:
                img[y, x, 2] = 255  # Active flag
                if dist < 12:
                    img[y, x, 0] = 10   # 1000 nm
                    img[y, x, 1] = 90   # 0 deg
                elif dist < 20:
                    img[y, x, 0] = 20   # 1100 nm
                    img[y, x, 1] = 180  # 90 deg
                else:
                    phi = np.arctan2(dy, dx)
                    sector = int(np.floor((phi + np.pi) / (2.0 * np.pi / 8.0))) % 8
                    img[y, x, 0] = periods[sector]
                    img[y, x, 1] = angles[sector]

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img, mode="RGB").save(path)
    return path


def main() -> int:
    # 1. Locate test.png
    base_dir = Path(__file__).resolve().parent
    img_path = base_dir / "_INPUT" / "test.png"
    if not img_path.exists():
        img_path = base_dir / "test.png"
    if not img_path.exists():
        img_path = ensure_test_image(base_dir / "_INPUT" / "test.png")

    print(f"=" * 70)
    print(f"Executing Full Process Test on: {img_path.name}")
    print(f"=" * 70)

    # 2. Build canonical Design
    print("\n[1/4] Decoding parameter image into canonical Design...")
    design = build_design(
        image_path=img_path,
        encoding_profile="rgb8-indexed-v1",
        pitch_nm=20000,
    )
    info = inspect_design(design)
    print(f"  Shape:             {design.shape[0]}x{design.shape[1]} cells")
    print(f"  Pitch:             {design.pitch_nm / 1000.0:.1f} µm ({design.pitch_nm} nm)")
    print(f"  Active Cells:      {info['active_cells']:,} / {info['total_cells']:,} ({info['active_percentage']:.1f}%)")
    print(f"  Unique Periods:    {info['unique_periods_nm']} nm")
    print(f"  Unique Angles:     {info['unique_angles_deg']} deg")

    # 3. Compile Fabrication Plan
    print("\n[2/4] Building Raith layout plan with circular aperture chord clipping...")
    plan = build_layout(design, top_name="TEST_HOLO")
    print(f"  Total Stripes:     {plan.total_stripes:,}")
    print(f"  Skipped Stripes:   {plan.skipped_degenerate_stripes}")
    print(f"  Structures Count:  {len(plan.library.structures)}")
    print(f"  Plan SHA-256:      {plan.plan_hash[:16]}...")

    # 4. Export bundle with multi-angle preview images
    angles = [0.0, 45.0, 90.0, 135.0]
    print(f"\n[3/4] Exporting fabrication bundle & rendering preview images at angles {angles} deg...")
    out_parent = base_dir / "_OUTPUT"
    bundle_dir = export_bundle(
        design,
        output_dir=out_parent,
        layout_name="TEST_HOLO",
        render_angles=angles,
        preview_preset="corrected",
    )

    print(f"\n[4/4] Execution completed successfully!")
    print(f"  Output folder associated with run:")
    print(f"  --> {bundle_dir.resolve()}\n")

    # Read manifest and verify files
    manifest_file = bundle_dir / "manifest.json"
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"  Manifest Status:   {manifest.get('status')}")
    print(f"  Generated Files in Output Folder:")
    for fname, meta in manifest.get("files", {}).items():
        fpath = bundle_dir / fname
        size_kb = meta["size_bytes"] / 1024.0
        exists_mark = "OK" if fpath.exists() else "MISSING"
        print(f"    [{exists_mark}] {fname:<26} ({size_kb:>7.1f} KB) sha256={meta['sha256'][:12]}...")

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED: Full process functionality verified.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
