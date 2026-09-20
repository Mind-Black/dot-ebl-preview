"""Small, UI-independent operations used by the Windows desktop interface."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

import numpy as np
from PIL import Image

from dot_ebl_preview.api import build_design, build_layout
from dot_ebl_preview.core.encoding import RGB8IndexedProfile, RGB16FixedProfile
from dot_ebl_preview.core.model import Design, OperationRecord
from dot_ebl_preview.io.artifacts import load_design_artifact
from dot_ebl_preview.io.images import save_image_rgb
from dot_ebl_preview.io.legacy_hls import import_legacy_hls, rgb_to_opencv_hls
from dot_ebl_preview.io.legacy_unity import (
    UNITY_LASER_HUES, UNITY_PERIOD_REAL_NM, import_legacy_unity_hsv,
)
from dot_ebl_preview.jobs.bundle import stage_and_export_bundle
from dot_ebl_preview.optics.presets import get_optical_preset
from dot_ebl_preview.preview.renderer import render_preview_image


INPUT_FORMATS = (
    "Holtida legacy HLS",
    "Learning Shaders HLS",
    "Unity HSV",
    "RGB8 indexed",
    "RGB16 fixed",
)


def load_gui_design(path: str | Path, image_format: str, pitch_um: float) -> Design:
    """Decode one image with the selected, explicit interpretation."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Design file not found: {source}")
    if source.suffix.lower() == ".npz":
        return load_design_artifact(source)
    if not math.isfinite(pitch_um) or pitch_um <= 0:
        raise ValueError("Holopixel pitch must be a positive number of micrometres.")
    pitch_nm = int(round(pitch_um * 1000.0))
    if pitch_nm <= 0:
        raise ValueError("Holopixel pitch is too small to represent in nanometres.")
    if image_format == "Holtida legacy HLS":
        return import_legacy_hls(source, preset="holtida-ebl", pitch_nm=pitch_nm)
    if image_format == "Learning Shaders HLS":
        return import_legacy_hls(source, preset="learning-shaders", pitch_nm=pitch_nm)
    if image_format == "Unity HSV":
        return import_legacy_unity_hsv(source, pitch_nm=pitch_nm)
    if image_format == "RGB8 indexed":
        return build_design(source, encoding_profile="rgb8-indexed-v1", pitch_nm=pitch_nm)
    if image_format == "RGB16 fixed":
        return build_design(source, encoding_profile="rgb16-fixed-v1", pitch_nm=pitch_nm)
    raise ValueError(f"Unknown image format: {image_format}")


def parameter_counts(design: Design, kind: Literal["gratings", "angles"]) -> list[tuple[float, int]]:
    """Distinct active parameters and their active-cell counts, sorted numerically."""
    values = design.period_nm if kind == "gratings" else design.angle_deg
    unique, counts = np.unique(values[design.active], return_counts=True)
    scale = 1000.0 if kind == "gratings" else 1.0
    return [(float(value) / scale, int(count)) for value, count in zip(unique, counts)]


def parameter_map(design: Design, kind: Literal["gratings", "angles"]) -> Image.Image:
    """Color map of active periods or angles. Inactive cells are dark gray."""
    if kind not in ("gratings", "angles"):
        raise ValueError(f"Unknown map type: {kind}")
    values = design.period_nm if kind == "gratings" else design.angle_deg
    rgb = np.full((*design.shape, 3), 24, dtype=np.uint8)
    if np.any(design.active):
        active_values = values[design.active].astype(np.float64)
        low, high = float(active_values.min()), float(active_values.max())
        level = (active_values - low) / (high - low) if high > low else np.full_like(active_values, 0.5)
        if kind == "gratings":
            colors = np.stack((255 * level, 100 + 110 * (1 - np.abs(2 * level - 1)), 255 * (1 - level)), axis=1)
        else:
            # A blue-to-red wheel makes neighboring orientations visible without changing the data.
            hue = (2.0 / 3.0) * (1.0 - level)
            sector = np.floor(hue * 6).astype(int)
            fraction = hue * 6 - sector
            q = 1 - fraction
            colors = np.empty((len(hue), 3), dtype=np.float64)
            palette = ((1, fraction, 0), (q, 1, 0), (0, 1, fraction),
                       (0, q, 1), (fraction, 0, 1), (1, 0, q))
            for index, components in enumerate(palette):
                chosen = sector % 6 == index
                if np.any(chosen):
                    colors[chosen] = np.stack([np.broadcast_to(x, hue.shape)[chosen] if not np.isscalar(x)
                                               else np.full(np.count_nonzero(chosen), x) for x in components], axis=1)
            colors *= 255
        rgb[design.active] = np.clip(np.round(colors), 0, 255).astype(np.uint8)
    return Image.fromarray(rgb, mode="RGB")


@dataclass(frozen=True)
class SceneSettings:
    """Scene positions in mm; directional angles point from design center outward."""

    light_pos: tuple[float, float, float] = (0.0, 229.430573, 327.660818)
    camera_pos: tuple[float, float, float] = (0.0, 0.0, 300.0)
    orientation_deg: float = 0.0
    aperture_mm: float = 2.0
    source_size_mm: float = 20.0

    def validated(self) -> "SceneSettings":
        values = (*self.light_pos, *self.camera_pos, self.orientation_deg, self.aperture_mm, self.source_size_mm)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Scene coordinates, orientation, aperture and source size must be finite numbers.")
        if self.light_pos == (0.0, 0.0, 0.0) or self.camera_pos == (0.0, 0.0, 0.0):
            raise ValueError("The source and observer must be away from the design center.")
        if self.aperture_mm < 0.0:
            raise ValueError("Observer aperture must be non-negative.")
        if self.source_size_mm < 0.0:
            raise ValueError("Light source physical size must be non-negative.")
        return self


def position_from_direction(azimuth_deg: float, elevation_deg: float, distance_mm: float) -> tuple[float, float, float]:
    """Convert a design-center-to-point direction and radius to an XYZ point in mm."""
    if not all(math.isfinite(v) for v in (azimuth_deg, elevation_deg, distance_mm)):
        raise ValueError("Direction and distance must be finite numbers.")
    if not -90 <= elevation_deg <= 90 or distance_mm <= 0:
        raise ValueError("Elevation must be between -90° and 90°; distance must be positive.")
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    horizontal = distance_mm * math.cos(elevation)
    return (horizontal * math.cos(azimuth), horizontal * math.sin(azimuth), distance_mm * math.sin(elevation))


def direction_from_position(position: tuple[float, float, float]) -> tuple[float, float, float]:
    """Convert a point in mm to outward azimuth, elevation, and distance."""
    if not all(math.isfinite(value) for value in position):
        raise ValueError("Position coordinates must be finite numbers.")
    x, y, z = position
    horizontal = math.hypot(x, y)
    distance = math.hypot(horizontal, z)
    if distance <= 0:
        raise ValueError("Position must be away from the design center.")
    return (math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, horizontal)), distance)


def render_scene(design: Design, settings: SceneSettings) -> Image.Image:
    """Run the CPU reference algorithm with the selected source, observer and rotation."""
    settings.validated()
    params = replace(
        get_optical_preset("corrected"),
        light_pos=settings.light_pos,
        camera_pos=settings.camera_pos,
        aperture_radius_factor=settings.aperture_mm,
        source_radius_factor=settings.source_size_mm,
    )
    rotated = replace(design, angle_deg=design.angle_deg + settings.orientation_deg)
    return render_preview_image(rotated, preset="corrected", params=params)


def render_scene_gpu(design: Design, settings: SceneSettings) -> Image.Image:
    """Run the OpenGL spectral renderer with the same physical scene settings."""
    settings.validated()
    from dot_ebl_preview.preview.gl_renderer import render_opengl_preview

    return render_opengl_preview(
        design,
        light_pos=settings.light_pos,
        camera_pos=settings.camera_pos,
        orientation_deg=settings.orientation_deg,
        aperture_mm=settings.aperture_mm,
        source_size_mm=settings.source_size_mm,
    )


def save_gds(design: Design, destination: str | Path) -> Path:
    """Create a GDS and publish it only after serialization succeeds."""
    output = Path(destination)
    if output.suffix.lower() != ".gds":
        raise ValueError("Choose a .gds output filename.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.stem}.{uuid4().hex}.tmp")
    try:
        plan = build_layout(design, top_name=output.stem)
        plan.library.write_gds(temp)
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    return output


def opencv_hls_to_rgb(h: np.ndarray, l: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Convert OpenCV HLS channels (H in 0..179, L in 0..255, S in 0..255) to uint8 RGB array."""
    h_deg = h.astype(np.float32) * 2.0
    l_val = l.astype(np.float32) / 255.0
    s_val = s.astype(np.float32) / 255.0

    c = (1.0 - np.abs(2.0 * l_val - 1.0)) * s_val
    h_prime = h_deg / 60.0
    x = c * (1.0 - np.abs(np.fmod(h_prime, 2.0) - 1.0))
    m = l_val - c / 2.0

    sector = np.floor(h_prime).astype(int) % 6
    shape = h.shape
    r = np.zeros(shape, dtype=np.float32)
    g = np.zeros(shape, dtype=np.float32)
    b = np.zeros(shape, dtype=np.float32)

    for sec, (rc, gc, bc) in enumerate([
        (c, x, 0.0), (x, c, 0.0), (0.0, c, x),
        (0.0, x, c), (x, 0.0, c), (c, 0.0, x),
    ]):
        cond = (sector == sec)
        r[cond] = rc if np.isscalar(rc) else rc[cond]
        g[cond] = gc if np.isscalar(gc) else gc[cond]
        b[cond] = bc if np.isscalar(bc) else bc[cond]

    rgb = np.stack([(r + m) * 255.0, (g + m) * 255.0, (b + m) * 255.0], axis=-1)
    return np.clip(np.round(rgb), 0, 255).astype(np.uint8)


def unity_hsv_to_rgb(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Convert HSV channels (H, S, V in 0..1) to uint8 RGB array."""
    h_norm = np.fmod(h.astype(np.float32), 1.0)
    h_norm = np.where(h_norm < 0.0, h_norm + 1.0, h_norm)
    s_val = np.clip(s.astype(np.float32), 0.0, 1.0)
    v_val = np.clip(v.astype(np.float32), 0.0, 1.0)

    c = v_val * s_val
    h_prime = h_norm * 6.0
    x = c * (1.0 - np.abs(np.fmod(h_prime, 2.0) - 1.0))
    m = v_val - c

    sector = np.floor(h_prime).astype(int) % 6
    shape = h.shape
    r = np.zeros(shape, dtype=np.float32)
    g = np.zeros(shape, dtype=np.float32)
    b = np.zeros(shape, dtype=np.float32)

    for sec, (rc, gc, bc) in enumerate([
        (c, x, 0.0), (x, c, 0.0), (0.0, c, x),
        (0.0, x, c), (x, 0.0, c), (c, 0.0, x),
    ]):
        cond = (sector == sec)
        r[cond] = rc if np.isscalar(rc) else rc[cond]
        g[cond] = gc if np.isscalar(gc) else gc[cond]
        b[cond] = bc if np.isscalar(bc) else bc[cond]

    rgb = np.stack([(r + m) * 255.0, (g + m) * 255.0, (b + m) * 255.0], axis=-1)
    return np.clip(np.round(rgb), 0, 255).astype(np.uint8)


def encode_gui_design_image(
    design: Design,
    image_format: str,
    original_rgb: np.ndarray | None = None,
) -> tuple[np.ndarray, Image.Image]:
    """Encode a Design to an image array and a PIL display image matching the chosen format."""
    h, w = design.shape
    if image_format == "RGB8 indexed":
        profile = RGB8IndexedProfile()
        try:
            raw_arr, _report = profile.encode(design, policy="quantize", allow_clip=True)
        except Exception:
            active = design.active
            uniq_p = sorted(set(design.period_nm[active].tolist())) if np.any(active) else [1000]
            uniq_a = sorted(set(design.angle_deg[active].tolist())) if np.any(active) else [0.0]
            dyn_profile = RGB8IndexedProfile(period_lut_nm=uniq_p[:256], angle_lut_deg=uniq_a[:256])
            raw_arr, _report = dyn_profile.encode(design, policy="quantize", allow_clip=True)
        return raw_arr, Image.fromarray(raw_arr, mode="RGB")

    if image_format == "RGB16 fixed":
        profile = RGB16FixedProfile()
        raw_arr, _report = profile.encode(design, policy="quantize")
        vis = np.zeros((h, w, 3), dtype=np.uint8)
        if np.any(design.active):
            act = design.active
            periods = raw_arr[act, 0].astype(np.float32)
            p_min, p_max = float(periods.min()), float(periods.max())
            if p_max > p_min:
                vis[act, 0] = np.clip(np.round((periods - p_min) / (p_max - p_min) * 255.0), 0, 255).astype(np.uint8)
            else:
                vis[act, 0] = 128
            vis[act, 1] = np.clip(raw_arr[act, 1] >> 8, 0, 255).astype(np.uint8)
            vis[act, 2] = 255
        return raw_arr, Image.fromarray(vis, mode="RGB")

    if image_format in ("Holtida legacy HLS", "Learning Shaders HLS"):
        rot_range = 180.0 if image_format == "Holtida legacy HLS" else 90.0
        h_arr = np.zeros((h, w), dtype=np.uint8)
        l_arr = np.zeros((h, w), dtype=np.uint8)
        s_arr = np.zeros((h, w), dtype=np.uint8)
        if np.any(design.active):
            p_um = design.period_nm[design.active] / 1000.0
            p_norm = np.clip((p_um - 0.9) / (1.2 - 0.9), 0.0, 1.0)
            idx = np.round(p_norm * 359).astype(int)
            h_arr[design.active] = (idx // 2).astype(np.uint8)
            sats = np.clip((design.angle_deg[design.active] / rot_range) * 100.0 + 50.0, 0.0, 100.0)
            s_arr[design.active] = np.clip(np.round(sats * 255.0 / 100.0), 0, 255).astype(np.uint8)
            if original_rgb is not None and original_rgb.shape[:2] == (h, w) and original_rgb.dtype == np.uint8:
                _h_orig, l_orig, _s_orig = rgb_to_opencv_hls(original_rgb)
                l_arr[design.active] = np.where((l_orig[design.active] > 0) & (l_orig[design.active] < 250),
                                                l_orig[design.active], 128)
            else:
                l_arr[design.active] = 128
        raw_arr = opencv_hls_to_rgb(h_arr, l_arr, s_arr)
        return raw_arr, Image.fromarray(raw_arr, mode="RGB")

    if image_format == "Unity HSV":
        min_angle, max_angle = -10.0, 10.0
        h_arr = np.zeros((h, w), dtype=np.float32)
        s_arr = np.zeros((h, w), dtype=np.float32)
        v_arr = np.zeros((h, w), dtype=np.float32)
        if np.any(design.active):
            act = design.active
            periods_nm = design.period_nm[act].astype(np.float32)
            laser_periods = np.array(UNITY_PERIOD_REAL_NM, dtype=np.float32)
            laser_hues = np.array(UNITY_LASER_HUES, dtype=np.float32)
            diffs = np.abs(periods_nm[:, None] - laser_periods[None, :])
            closest_indices = np.argmin(diffs, axis=1)
            h_arr[act] = laser_hues[closest_indices]
            s_norm = np.clip((design.angle_deg[act] - min_angle) / (max_angle - min_angle), 0.0, 1.0)
            s_arr[act] = s_norm
            v_arr[act] = 1.0
        raw_arr = unity_hsv_to_rgb(h_arr, s_arr, v_arr)
        return raw_arr, Image.fromarray(raw_arr, mode="RGB")

    # Fallback
    raw_arr, _report = RGB8IndexedProfile().encode(design, policy="quantize", allow_clip=True)
    return raw_arr, Image.fromarray(raw_arr, mode="RGB")


def apply_parameter_edit(
    design: Design,
    kind: Literal["gratings", "angles"],
    old_val: float,
    new_val: float,
) -> tuple[Design, int]:
    """Update a grating period or angle across all matching active cells."""
    if kind == "gratings":
        if not math.isfinite(new_val) or new_val <= 0:
            raise ValueError("Grating period must be a positive number of micrometres.")
        old_nm = int(round(old_val * 1000.0))
        new_nm = int(round(new_val * 1000.0))
        if new_nm <= 0:
            raise ValueError("Grating period is too small to represent in nanometres.")
        mask = design.active & (design.period_nm == old_nm)
        count = int(np.count_nonzero(mask))
        if count > 0:
            design.period_nm[mask] = new_nm
            design.operations.append(OperationRecord("edit_grating", {"old_nm": old_nm, "new_nm": new_nm, "cells": count}))
        return design, count
    elif kind == "angles":
        if not math.isfinite(new_val):
            raise ValueError("Angle must be a finite number of degrees.")
        mask = design.active & np.isclose(design.angle_deg, old_val, atol=1e-5)
        count = int(np.count_nonzero(mask))
        if count > 0:
            design.angle_deg[mask] = new_val
            design.operations.append(OperationRecord("edit_angle", {"old_deg": old_val, "new_deg": new_val, "cells": count}))
        return design, count
    else:
        raise ValueError(f"Unknown parameter kind: {kind}")


def save_gui_design_image(
    path: str | Path,
    raw_array: np.ndarray,
) -> Path:
    """Save an encoded design image array losslessly."""
    output = Path(path)
    if output.suffix.lower() != ".png":
        raise ValueError("Choose a .png output filename.")
    save_image_rgb(output, raw_array)
    return output


def export_gui_bundle(design: Design, destination_dir: str | Path, layout_name: str = "HOLOGRAM") -> Path:
    """Publish a complete fabrication bundle for the current design."""
    return stage_and_export_bundle(design, output_parent_dir=destination_dir, layout_name=layout_name)
