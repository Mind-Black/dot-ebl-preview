"""CPU spectral optical reference engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
from numpy.typing import NDArray

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.optics.tables import (
    XYZ2RGB,
    bluexyY,
    greenxyY,
    premultiplied_XYZ,
    redxyY,
    stdIllum,
)


def _get_intersection(
    x1: float, y1: float, x2: float, y2: float,
    x3: float, y3: float, x4: float, y4: float,
) -> Tuple[float, float]:
    """Find line-line intersection of (x1,y1)-(x2,y2) and (x3,y3)-(x4,y4)."""
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return x1, y1
    int_x = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
    int_y = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
    return int_x, int_y


def _point_inside_triangle(pt: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> bool:
    """Test whether point pt is inside triangle abc."""
    px, py = pt
    ax, ay = a
    bx, by = b
    cx, cy = c

    as_x = px - ax
    as_y = py - ay

    s_ab = (bx - ax) * as_y - (by - ay) * as_x > 0
    if ((cx - ax) * as_y - (cy - ay) * as_x > 0) == s_ab:
        return False
    if ((cx - bx) * (py - by) - (cy - by) * (px - bx) > 0) != s_ab:
        return False
    return True


@dataclass
class OpticalSimParams:
    """Parameters for the spectral optical simulation engine.

    Notes on Deferred Optical Features:
        TODO(Optics): Calibrated single-pixel line diffraction efficiency.
        The current model assumes ideal thin binary diffraction with equal efficiency across
        grating periods, modulated only by diffraction order coefficients (order 1 = 1.0,
        order 2 = 1/15) and bulk nickel spectral reflectance. Rigorous modeling (RCWA or FDTD)
        accounting for physical line width (beam footprint), resist etch depth, and groove
        profile is deferred pending experimental scatterometry measurements.

        TODO(Optics): Spatially extended light sources and diffuse BRDF.
        The current implementation treats illumination and viewing as directional rays from
        point coordinates (light_pos, camera_pos). Spatially extended area illuminants and
        substrate diffuse scattering (BRDF) are deferred.

        TODO(Optics): GPU GLSL fragment/compute shader instancing.
        Headless CPU evaluation is implemented; real-time 60 FPS evaluation of 77 wavelength
        bands on the GPU is deferred to Phase 3.
    """
    orders: Tuple[int, ...] = (-1, 1)
    include_order_2: bool = False
    order_2_weight: float = 1.0 / 15.0
    camera_pos: Tuple[float, float, float] = (0.0, 0.0, 66.0)
    light_pos: Tuple[float, float, float] = (
        0.0,
        float(36.0 * math.sin(math.radians(35.0))),
        float(36.0 * math.cos(math.radians(35.0))),
    )
    aperture_radius_factor: float = 5.0
    apply_gamut_mapping: bool = True
    unity_mode: bool = False


def simulate_cell_optical_color(
    period_nm: int,
    angle_deg: float,
    world_pos: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    params: Optional[OpticalSimParams] = None,
) -> Tuple[float, float, float]:
    """Calculate the rendered sRGB color (r, g, b in [0, 1]) for a single holopixel.

    Simulates diffraction across 77 discrete spectral wavelength bands (380 nm to 760 nm
    in 5 nm increments) under standard illuminant D65, factoring in CIE 1931 color matching
    functions, nickel spectral reflectance, and sRGB gamut boundary mapping.

    Args:
        period_nm: Grating period in integer nanometres.
        angle_deg: Grating orientation in degrees (CCW rotation from +X axis).
        world_pos: 3D coordinates (x, y, z) of the cell center in the scene.
        params: Optical simulation parameters (camera, light, aperture, orders).

    Returns:
        Tuple[float, float, float]: Linear sRGB color tuple with components clamped to [0.0, 1.0].
    """
    if period_nm <= 0:
        return 0.0, 0.0, 0.0

    if params is None:
        params = OpticalSimParams()

    sxyz_table = premultiplied_XYZ()  # (77, 3)
    xyz2rgb_mat = XYZ2RGB()           # (3, 3)

    # Geometry & vectors
    # Holopixel coordinate: grating normal is rotated by angle_deg CCW from +Y
    rad = math.radians(angle_deg)
    grating_vec = (math.sin(rad), math.cos(rad), 0.0)

    # World position and unit normal
    unit_normal = (0.0, 0.0, 1.0)

    # Light vector
    lx = params.light_pos[0] - world_pos[0]
    ly = params.light_pos[1] - world_pos[1]
    lz = params.light_pos[2] - world_pos[2]
    l_len = math.sqrt(lx * lx + ly * ly + lz * lz)
    if l_len < 1e-9:
        l_len = 1.0
    unit_light = (lx / l_len, ly / l_len, lz / l_len)

    # Camera vector
    cx = params.camera_pos[0] - world_pos[0]
    cy = params.camera_pos[1] - world_pos[1]
    cz = params.camera_pos[2] - world_pos[2]
    c_len = math.sqrt(cx * cx + cy * cy + cz * cz)
    if c_len < 1e-9:
        c_len = 1.0
    unit_cam = (cx / c_len, cy / c_len, cz / c_len)

    radius = params.aperture_radius_factor / c_len

    actual_light = (unit_light[0] + unit_normal[0], unit_light[1] + unit_normal[1])
    cam_x = unit_cam[0] + unit_normal[0]
    cam_y = unit_cam[1] + unit_normal[1]
    cam_z_sq = max(0.0, 1.0 - cam_x * cam_x - cam_y * cam_y)
    actual_cam = (cam_x, cam_y, math.sqrt(cam_z_sq))

    period_m = period_nm * 1e-9
    s_factor = grating_vec[0] / period_m
    c_factor = grating_vec[1] / period_m

    orders_to_check: List[int] = list(params.orders)
    if params.include_order_2:
        orders_to_check = [-2, -1, 1, 2]

    xyz_acc = np.zeros(3, dtype=np.float64)
    light_xyz_acc = np.zeros(3, dtype=np.float64)

    # 77 wavelength samples from 380 nm to 760 nm in 5 nm steps
    for counter in range(77):
        wl = 380.0 + counter * 5.0
        wl_m = wl * 1e-9
        s_xyz = sxyz_table[counter].astype(np.float64)

        for m in orders_to_check:
            if m == 0:
                continue
            coeff = params.order_2_weight if abs(m) == 2 else 1.0

            alpha_x = m * wl_m * s_factor - actual_light[0]
            alpha_y = -m * wl_m * c_factor - actual_light[1]
            alpha12 = alpha_x * alpha_x + alpha_y * alpha_y

            if alpha12 < 1.0:
                alpha_z = math.sqrt(1.0 - alpha12)
                # Distance to actualCameraDirection
                dx = actual_cam[0] - alpha_x
                dy = actual_cam[1] - alpha_y
                dz = actual_cam[2] - alpha_z
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dist <= radius:
                    xyz_acc += s_xyz * coeff

        light_xyz_acc += s_xyz

    # Illuminant normalization
    if light_xyz_acc[1] > 1e-9:
        xyz_acc /= light_xyz_acc[1]
    else:
        return 0.0, 0.0, 0.0

    xyz_sum = xyz_acc[0] + xyz_acc[1] + xyz_acc[2]
    if xyz_sum < 1e-9:
        return 0.0, 0.0, 0.0

    x_chroma = xyz_acc[0] / xyz_sum
    y_chroma = xyz_acc[1] / xyz_sum

    if params.apply_gamut_mapping:
        red_pt = (float(redxyY()[0]), float(redxyY()[1]))
        grn_pt = (float(greenxyY()[0]), float(greenxyY()[1]))
        blu_pt = (float(bluexyY()[0]), float(bluexyY()[1]))

        if not _point_inside_triangle((x_chroma, y_chroma), red_pt, blu_pt, grn_pt):
            l_sum = light_xyz_acc[0] + light_xyz_acc[1] + light_xyz_acc[2]
            if l_sum < 1e-9:
                return 0.0, 0.0, 0.0
            d65 = (light_xyz_acc[0] / l_sum, light_xyz_acc[1] / l_sum)

            int_bg = _get_intersection(x_chroma, y_chroma, d65[0], d65[1], blu_pt[0], blu_pt[1], grn_pt[0], grn_pt[1])
            int_gr = _get_intersection(x_chroma, y_chroma, d65[0], d65[1], grn_pt[0], grn_pt[1], red_pt[0], red_pt[1])
            int_rb = _get_intersection(x_chroma, y_chroma, d65[0], d65[1], red_pt[0], red_pt[1], blu_pt[0], blu_pt[1])

            # Inset slightly towards white point (0.99)
            d65_bg = ((int_bg[0] - d65[0]) * 0.99 + d65[0], (int_bg[1] - d65[1]) * 0.99 + d65[1])
            d65_gr = ((int_gr[0] - d65[0]) * 0.99 + d65[0], (int_gr[1] - d65[1]) * 0.99 + d65[1])
            d65_rb = ((int_rb[0] - d65[0]) * 0.99 + d65[0], (int_rb[1] - d65[1]) * 0.99 + d65[1])

            closest = 1e7
            x_new, y_new = x_chroma, y_chroma

            for cand in [d65_bg, d65_gr, d65_rb]:
                dist = math.hypot(x_chroma - cand[0], y_chroma - cand[1])
                if dist < closest and _point_inside_triangle(cand, red_pt, blu_pt, grn_pt):
                    closest = dist
                    x_new, y_new = cand

            if closest >= 1e6:
                # If no boundary intersection point was strictly inside the gamut triangle, fall back to D65
                x_new, y_new = d65

            if y_new > 1e-9:
                xyz_acc[0] = xyz_acc[1] * x_new / y_new
                xyz_acc[2] = xyz_acc[1] * (1.0 - x_new - y_new) / y_new

    # Convert XYZ to RGB
    rgb = np.dot(xyz2rgb_mat, xyz_acc)
    r_out = float(np.clip(rgb[0], 0.0, 1.0))
    g_out = float(np.clip(rgb[1], 0.0, 1.0))
    b_out = float(np.clip(rgb[2], 0.0, 1.0))

    return r_out, g_out, b_out


def render_optical_preview(
    design: Design,
    params: Optional[OpticalSimParams] = None,
) -> NDArray[np.float32]:
    """Render full 2D optical preview image as float32 array in shape (H, W, 3)."""
    h, w = design.shape
    preview = np.zeros((h, w, 3), dtype=np.float32)

    active = design.active
    if not np.any(active):
        if design.fallback_intensity is not None:
            for c in range(3):
                preview[:, :, c] = design.fallback_intensity
        return preview

    if params is None:
        params = OpticalSimParams()

    # Optimization: compute optical color per unique active (period, angle) key
    cache = {}
    active_rows, active_cols = np.nonzero(active)

    for r, c in zip(active_rows, active_cols):
        p = int(design.period_nm[r, c])
        a = float(design.angle_deg[r, c])
        key = (p, round(a, 3))

        if key not in cache:
            cache[key] = simulate_cell_optical_color(p, a, params=params)

        rgb = cache[key]

        # In Unity preset: if all RGB <= 0.01 and fallback available, apply fallback
        if params.unity_mode and (rgb[0] <= 0.01 and rgb[1] <= 0.01 and rgb[2] <= 0.01):
            if design.fallback_intensity is not None:
                fb = float(design.fallback_intensity[r, c])
                rgb = (fb, fb, fb)

        preview[r, c, :] = rgb

    # For inactive cells with fallback intensity, fill with fallback
    inactive = ~active
    if design.fallback_intensity is not None and np.any(inactive):
        for c in range(3):
            preview[inactive, c] = design.fallback_intensity[inactive]

    return preview
