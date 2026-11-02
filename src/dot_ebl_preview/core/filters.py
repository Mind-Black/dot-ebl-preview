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


def apply_masked_bilateral_filter(
    design: Design,
    diameter: int = 3,
    sigma_color_period: float = 50.0,
    sigma_color_angle: float = 10.0,
    sigma_space: float = 100.0,
    filter_period: bool = True,
    filter_angle: bool = True,
) -> Design:
    """Apply valid-only masked bilateral filtering to design period (scalar) and angle (axial).

    Args:
        design: input Design
        diameter: kernel diameter (must be >= 1; diameter <= 1 returns design copy)
        sigma_color_period: range standard deviation for period values in nm (default: 50.0)
        sigma_color_angle: range standard deviation for grating orientation in deg (default: 10.0)
        sigma_space: spatial standard deviation in pixels (default: 100.0)
        filter_period: whether to filter period_nm (default: True)
        filter_angle: whether to filter angle_deg (default: True)

    Valid-only masking strictly excludes inactive cells (active == False) so background zeros
    do not bleed into the boundaries of active shapes.
    Period filtering uses a valid-only scalar bilateral filter.
    Angle filtering uses a valid-only axial (doubled-angle vector) bilateral filter with nearest-branch lifting.
    """
    new_design = design.copy()
    h, w = new_design.shape
    active = new_design.active
    orig_periods = new_design.period_nm.copy()
    orig_angles = new_design.angle_deg.copy()

    if not np.any(active) or diameter <= 1 or (not filter_period and not filter_angle):
        return new_design
    if sigma_space <= 0.0 or (filter_period and sigma_color_period <= 0.0) or (filter_angle and sigma_color_angle <= 0.0):
        return new_design

    radius = diameter // 2
    y, x = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    spatial_dist_sq = (x * x + y * y).astype(np.float64)
    spatial_kernel = np.exp(-spatial_dist_sq / (2.0 * sigma_space * sigma_space))

    pad_active = np.pad(active, radius, mode="constant", constant_values=False)
    pad_periods = np.pad(orig_periods.astype(np.float64), radius, mode="constant", constant_values=0.0)
    pad_angles = np.pad(orig_angles, radius, mode="constant", constant_values=0.0)

    smoothed_periods = orig_periods.copy()
    smoothed_angles = orig_angles.copy()

    for r in range(h):
        for c in range(w):
            if not active[r, c]:
                continue
            sub_act = pad_active[r : r + 2 * radius + 1, c : c + 2 * radius + 1]

            # 1. Period scalar bilateral filter
            if filter_period:
                center_p = float(orig_periods[r, c])
                sub_p = pad_periods[r : r + 2 * radius + 1, c : c + 2 * radius + 1]
                diff_p = sub_p - center_p
                w_color_p = np.exp(-(diff_p ** 2) / (2.0 * sigma_color_period * sigma_color_period))
                total_w_p = spatial_kernel * w_color_p * sub_act
                sum_w_p = np.sum(total_w_p)
                if sum_w_p > 1e-9:
                    smoothed_val = np.sum(total_w_p * sub_p) / sum_w_p
                    smoothed_periods[r, c] = int(np.floor(smoothed_val + 0.5) if smoothed_val >= 0 else np.ceil(smoothed_val - 0.5))
                else:
                    smoothed_periods[r, c] = orig_periods[r, c]

            # 2. Angle axial bilateral filter
            if filter_angle:
                center_ang = float(orig_angles[r, c])
                sub_ang = pad_angles[r : r + 2 * radius + 1, c : c + 2 * radius + 1]
                # Directed angle distance modulo 180
                diff_ang = (sub_ang - center_ang + 90.0) % 180.0 - 90.0
                w_color_a = np.exp(-(diff_ang ** 2) / (2.0 * sigma_color_angle * sigma_color_angle))
                total_w_a = spatial_kernel * w_color_a * sub_act
                sum_w_a = np.sum(total_w_a)
                if sum_w_a > 1e-9:
                    rad_doubled = np.radians(2.0 * sub_ang)
                    sin_sum = np.sum(total_w_a * np.sin(rad_doubled))
                    cos_sum = np.sum(total_w_a * np.cos(rad_doubled))
                    mag = np.hypot(sin_sum, cos_sum)
                    if mag < 1e-6:
                        smoothed_angles[r, c] = center_ang
                    else:
                        th2 = np.degrees(np.arctan2(sin_sum, cos_sum))
                        smoothed_angles[r, c] = _lift_to_nearest_branch(th2 / 2.0, center_ang)
                else:
                    smoothed_angles[r, c] = center_ang

    if filter_period:
        new_design.period_nm[active] = smoothed_periods[active]
    if filter_angle:
        new_design.angle_deg[active] = smoothed_angles[active]

    new_design.operations.append(
        OperationRecord(
            name="apply_masked_bilateral_filter",
            params={
                "diameter": diameter,
                "sigma_color_period": sigma_color_period,
                "sigma_color_angle": sigma_color_angle,
                "sigma_space": sigma_space,
                "filter_period": filter_period,
                "filter_angle": filter_angle,
            },
        )
    )
    return new_design
