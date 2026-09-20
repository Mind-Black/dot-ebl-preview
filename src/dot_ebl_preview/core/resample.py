"""Nearest-neighbor resampling and downscaling."""

from __future__ import annotations

from typing import Tuple
import numpy as np
from numpy.typing import NDArray

from dot_ebl_preview.core.model import Design, OperationRecord


def downscale_design(design: Design, factor: int) -> Design:
    """Downscale a Design by integer factor using nearest-neighbor indexing.

    Preserves exact discrete values and activity mask.
    New dimensions: new_height = orig_height // factor, new_width = orig_width // factor.
    """
    if factor <= 0:
        raise ValueError(f"Downscale factor must be positive integer, got {factor}")
    if factor == 1:
        return design.copy()

    h, w = design.shape
    new_h = h // factor
    new_w = w // factor
    if new_h == 0 or new_w == 0:
        raise ValueError(f"Downscale factor {factor} too large for design of shape {design.shape}")

    # Nearest neighbor row/col indices (matching OpenCV INTER_NEAREST: floor(index * factor))
    row_indices = np.arange(new_h) * factor
    col_indices = np.arange(new_w) * factor

    grid_r, grid_c = np.ix_(row_indices, col_indices)

    new_period = design.period_nm[grid_r, grid_c].copy()
    new_angle = design.angle_deg[grid_r, grid_c].copy()
    new_active = design.active[grid_r, grid_c].copy()

    new_masks = {}
    for k, v in design.region_masks.items():
        new_masks[k] = v[grid_r, grid_c].copy()

    new_appearance = None
    if design.appearance_rgb is not None:
        new_appearance = design.appearance_rgb[grid_r, grid_c, :].copy()

    new_fallback = None
    if design.fallback_intensity is not None:
        new_fallback = design.fallback_intensity[grid_r, grid_c].copy()

    new_design = Design(
        shape=(new_h, new_w),
        pitch_nm=design.pitch_nm,
        period_nm=new_period,
        angle_deg=new_angle,
        active=new_active,
        exposure_mode=design.exposure_mode,
        layer=design.layer,
        dose=design.dose,
        region_masks=new_masks,
        appearance_rgb=new_appearance,
        fallback_intensity=new_fallback,
        source_identity=design.source_identity,
        operations=list(design.operations),
    )
    new_design.operations.append(
        OperationRecord(
            name="downscale",
            params={"factor": factor, "orig_shape": (h, w), "new_shape": (new_h, new_w)},
        )
    )
    return new_design
