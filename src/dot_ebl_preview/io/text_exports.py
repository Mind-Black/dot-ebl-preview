"""Legacy parameter text outputs (angles.txt and gratings.txt)."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union
import numpy as np

from dot_ebl_preview.core.model import Design


def export_text_parameters(
    output_dir: Union[str, Path],
    design: Design,
    invalid_period_sentinel: float = 0.0,
    invalid_angle_sentinel: float = -1000.0,
) -> Tuple[Path, Path]:
    """Export angles.txt (degrees) and gratings.txt (µm) with legacy sentinels.

    Returns:
      (angles_path, gratings_path)
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    h, w = design.shape
    active = design.active

    # Gratings in micrometres
    gratings = np.full((h, w), invalid_period_sentinel, dtype=np.float64)
    gratings[active] = design.period_nm[active] / 1000.0

    # Angles in degrees
    angles = np.full((h, w), invalid_angle_sentinel, dtype=np.float64)
    angles[active] = design.angle_deg[active]

    angles_path = out / "angles.txt"
    gratings_path = out / "gratings.txt"

    np.savetxt(angles_path, angles, fmt="%.6f")
    np.savetxt(gratings_path, gratings, fmt="%.6f")

    return angles_path, gratings_path
