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
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.io.artifacts import load_design_artifact
from dot_ebl_preview.io.legacy_hls import import_legacy_hls
from dot_ebl_preview.io.legacy_unity import import_legacy_unity_hsv
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

    light_pos: tuple[float, float, float] = (0.0, 20.6487533, 29.4891314)
    camera_pos: tuple[float, float, float] = (0.0, 0.0, 66.0)
    orientation_deg: float = 0.0

    def validated(self) -> "SceneSettings":
        values = (*self.light_pos, *self.camera_pos, self.orientation_deg)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Scene coordinates and orientation must be finite numbers.")
        if self.light_pos == (0.0, 0.0, 0.0) or self.camera_pos == (0.0, 0.0, 0.0):
            raise ValueError("The source and observer must be away from the design center.")
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
    params = replace(get_optical_preset("corrected"), light_pos=settings.light_pos, camera_pos=settings.camera_pos)
    rotated = replace(design, angle_deg=design.angle_deg + settings.orientation_deg)
    return render_preview_image(rotated, preset="corrected", params=params)


def render_scene_gpu(design: Design, settings: SceneSettings) -> Image.Image:
    """Run the OpenGL spectral renderer with the same physical scene settings."""
    settings.validated()
    from dot_ebl_preview.preview.gl_renderer import render_opengl_preview

    return render_opengl_preview(
        design, light_pos=settings.light_pos, camera_pos=settings.camera_pos,
        orientation_deg=settings.orientation_deg,
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
