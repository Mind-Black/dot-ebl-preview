"""Radial gradient overrides and region-based operations."""

from __future__ import annotations

from typing import Optional, Tuple
import numpy as np
from numpy.typing import NDArray

from dot_ebl_preview.core.model import Design, OperationRecord


def apply_radial_gradient(
    design: Design,
    mask: Optional[NDArray[np.bool_]] = None,
    base_angle_deg: float = -15.0,
    span_angle_deg: float = 40.0,
    center_offset_y_px: int = 50,
    center_offset_x_px: int = 0,
    preset_name: Optional[str] = None,
) -> Design:
    """Apply radial gradient angle override over a selected mask.

    Presets:
      - 'holtida-ebl': base=-15.0, span=40.0, center_offset_y=50, center_offset_x=0
      - 'learning-shaders': base=-5.0, span=25.0, center_offset_y=50, center_offset_x=0

    Coordinates:
      Calculated in cell pixel coordinates on the design grid.
      center_y = height // 2 + center_offset_y_px
      center_x = width // 2 + center_offset_x_px
      distance = sqrt((x - center_x)^2 + (y - center_y)^2)
      max_dist = sqrt(center_x^2 + center_y^2)
      angle = base_angle_deg + (distance / max_dist) * span_angle_deg
    """
    if preset_name == "holtida-ebl":
        base_angle_deg = -15.0
        span_angle_deg = 40.0
        center_offset_y_px = 50
        center_offset_x_px = 0
    elif preset_name == "learning-shaders":
        base_angle_deg = -5.0
        span_angle_deg = 25.0
        center_offset_y_px = 50
        center_offset_x_px = 0

    new_design = design.copy()
    h, w = new_design.shape

    if mask is None:
        if "hue_162" in new_design.region_masks:
            mask = new_design.region_masks["hue_162"]
        else:
            # If no mask specified and no hue_162 mask, apply to all active
            mask = new_design.active

    if mask.shape != (h, w):
        raise ValueError(f"Mask shape {mask.shape} does not match design shape {new_design.shape}")

    if not np.any(mask):
        return new_design

    center_y = h // 2 + center_offset_y_px
    center_x = w // 2 + center_offset_x_px

    y_coords, x_coords = np.ogrid[:h, :w]
    distance = np.sqrt((x_coords - center_x) ** 2 + (y_coords - center_y) ** 2)
    max_dist = np.sqrt(center_x ** 2 + center_y ** 2)
    if max_dist == 0:
        max_dist = 1.0

    radial_angles = base_angle_deg + (distance / max_dist) * span_angle_deg
    new_design.angle_deg[mask] = radial_angles[mask]

    new_design.operations.append(
        OperationRecord(
            name="apply_radial_gradient",
            params={
                "base_angle_deg": base_angle_deg,
                "span_angle_deg": span_angle_deg,
                "center_offset_y_px": center_offset_y_px,
                "center_offset_x_px": center_offset_x_px,
                "affected_pixels": int(np.count_nonzero(mask)),
            },
        )
    )
    return new_design
