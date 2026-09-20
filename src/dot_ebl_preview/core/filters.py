"""Masked Gaussian and bilateral smoothing filters with axial orientation unwrapping."""

from __future__ import annotations

from typing import Literal, Optional, Tuple
import numpy as np
from numpy.typing import NDArray

from dot_ebl_preview.core.model import Design, OperationRecord


def _lift_to_nearest_branch(theta_axial: float, theta_orig: float) -> float:
    """Lift an axial angle (modulo 180°) to the branch nearest to theta_orig.

    Candidate branches are theta_axial + k * 180 for k in integer.
    Ties broken by choosing the numerically lower directed angle.
    """
    # Bring theta_axial to [-90, +90]
    base = ((theta_axial + 90.0) % 180.0) - 90.0
    # Search nearby branches centered around theta_orig
    k_center = int(round((theta_orig - base) / 180.0))
    best_branch = base
    best_dist = float("inf")

    for k in [k_center - 1, k_center, k_center + 1]:
        cand = base + k * 180.0
        dist = abs(cand - theta_orig)
        if dist < best_dist - 1e-9:
            best_dist = dist
            best_branch = cand
        elif abs(dist - best_dist) <= 1e-9:
            # Deterministic tie: choose numerically lower branch
            if cand < best_branch:
                best_branch = cand

    return best_branch


def apply_gaussian_filter(
    design: Design,
    sigma: float = 1.0,
    mode: Literal["scalar", "axial"] = "axial",
    radius: Optional[int] = None,
) -> Design:
    """Apply valid-only Gaussian smoothing to design angles.

    Args:
      design: input Design
      sigma: standard deviation of Gaussian kernel
      mode: 'scalar' (direct angle smoothing) or 'axial' (doubled-angle vector smoothing with nearest-branch lift)
      radius: kernel half-width in pixels (defaults to int(ceil(3*sigma)))
    """
    new_design = design.copy()
    h, w = new_design.shape
    active = new_design.active
    orig_angles = new_design.angle_deg.copy()

    if not np.any(active) or sigma <= 0 or (radius is not None and radius <= 0):
        return new_design

    if radius is None:
        radius = max(1, int(np.ceil(3.0 * sigma)))

    # Generate 1D / 2D Gaussian kernel
    y, x = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    kernel = np.exp(-(x * x + y * y) / (2.0 * sigma * sigma))

    smoothed_angles = orig_angles.copy()

    # Pre-pad arrays for valid-only convolution
    pad_active = np.pad(active, radius, mode="constant", constant_values=False)

    if mode == "scalar":
        pad_angles = np.pad(orig_angles, radius, mode="constant", constant_values=0.0)
        for r in range(h):
            for c in range(w):
                if not active[r, c]:
                    continue
                sub_act = pad_active[r : r + 2 * radius + 1, c : c + 2 * radius + 1]
                sub_ang = pad_angles[r : r + 2 * radius + 1, c : c + 2 * radius + 1]
                w_eff = kernel * sub_act
                sum_w = np.sum(w_eff)
                if sum_w > 1e-9:
                    smoothed_angles[r, c] = np.sum(w_eff * sub_ang) / sum_w
                else:
                    smoothed_angles[r, c] = orig_angles[r, c]
    else:  # axial mode
        rad_orig = np.radians(orig_angles)
        sin_2theta = np.sin(2.0 * rad_orig)
        cos_2theta = np.cos(2.0 * rad_orig)

        pad_sin = np.pad(sin_2theta, radius, mode="constant", constant_values=0.0)
        pad_cos = np.pad(cos_2theta, radius, mode="constant", constant_values=0.0)

        for r in range(h):
            for c in range(w):
                if not active[r, c]:
                    continue
                sub_act = pad_active[r : r + 2 * radius + 1, c : c + 2 * radius + 1]
                w_eff = kernel * sub_act
                sum_w = np.sum(w_eff)
                if sum_w <= 1e-9:
                    smoothed_angles[r, c] = orig_angles[r, c]
                    continue

                sub_sin = pad_sin[r : r + 2 * radius + 1, c : c + 2 * radius + 1]
                sub_cos = pad_cos[r : r + 2 * radius + 1, c : c + 2 * radius + 1]

                sum_sin = np.sum(w_eff * sub_sin)
                sum_cos = np.sum(w_eff * sub_cos)
                magnitude = np.hypot(sum_sin, sum_cos)

                if magnitude < 1e-6:
                    # Near-zero resultant: retain original angle
                    smoothed_angles[r, c] = orig_angles[r, c]
                else:
                    theta_2 = np.degrees(np.arctan2(sum_sin, sum_cos))
                    theta_axial = theta_2 / 2.0
                    # Lift to branch nearest to original angle
                    lifted = _lift_to_nearest_branch(theta_axial, orig_angles[r, c])
                    smoothed_angles[r, c] = lifted

    new_design.angle_deg[active] = smoothed_angles[active]
    new_design.operations.append(
        OperationRecord(
            name="apply_gaussian_filter",
            params={"sigma": sigma, "mode": mode, "radius": radius},
        )
    )
    return new_design


def apply_bilateral_filter(
    design: Design,
    diameter: int = 3,
    sigma_color: float = 10.0,
    sigma_space: float = 100.0,
    mode: Literal["scalar", "axial"] = "scalar",
) -> Design:
    """Apply valid-only Bilateral smoothing to design angles.

    Matches Holtida-EBL parameters: d=3, sigmaColor=10, sigmaSpace=100.
    """
    new_design = design.copy()
    h, w = new_design.shape
    active = new_design.active
    orig_angles = new_design.angle_deg.copy()

    if not np.any(active) or diameter <= 1 or sigma_color <= 0.0 or sigma_space <= 0.0:
        return new_design

    radius = diameter // 2
    y, x = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    spatial_dist_sq = (x * x + y * y).astype(np.float64)
    spatial_kernel = np.exp(-spatial_dist_sq / (2.0 * sigma_space * sigma_space))

    pad_active = np.pad(active, radius, mode="constant", constant_values=False)
    pad_angles = np.pad(orig_angles, radius, mode="constant", constant_values=0.0)

    smoothed_angles = orig_angles.copy()

    for r in range(h):
        for c in range(w):
            if not active[r, c]:
                continue
            center_ang = orig_angles[r, c]
            sub_act = pad_active[r : r + 2 * radius + 1, c : c + 2 * radius + 1]
            sub_ang = pad_angles[r : r + 2 * radius + 1, c : c + 2 * radius + 1]

            if mode == "scalar":
                color_diff = sub_ang - center_ang
            else:
                # Directed angle distance modulo 180
                diff = (sub_ang - center_ang + 90.0) % 180.0 - 90.0
                color_diff = diff

            color_weights = np.exp(-(color_diff ** 2) / (2.0 * sigma_color * sigma_color))
            total_w = spatial_kernel * color_weights * sub_act
            sum_w = np.sum(total_w)

            if sum_w > 1e-9:
                if mode == "scalar":
                    smoothed_angles[r, c] = np.sum(total_w * sub_ang) / sum_w
                else:
                    rad_diff = np.radians(2.0 * sub_ang)
                    sin_sum = np.sum(total_w * np.sin(rad_diff))
                    cos_sum = np.sum(total_w * np.cos(rad_diff))
                    mag = np.hypot(sin_sum, cos_sum)
                    if mag < 1e-6:
                        smoothed_angles[r, c] = center_ang
                    else:
                        th2 = np.degrees(np.arctan2(sin_sum, cos_sum))
                        smoothed_angles[r, c] = _lift_to_nearest_branch(th2 / 2.0, center_ang)
            else:
                smoothed_angles[r, c] = center_ang

    new_design.angle_deg[active] = smoothed_angles[active]
    new_design.operations.append(
        OperationRecord(
            name="apply_bilateral_filter",
            params={
                "diameter": diameter,
                "sigma_color": sigma_color,
                "sigma_space": sigma_space,
                "mode": mode,
            },
        )
    )
    return new_design
