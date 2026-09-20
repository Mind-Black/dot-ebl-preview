"""Optical preview renderer with headless CPU mode and optional OpenGL support."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.optics.engine import OpticalSimParams, render_optical_preview


def linear_to_srgb(c: Union[float, NDArray[np.floating]]) -> NDArray[np.floating]:
    """Convert linear RGB float values in [0.0, 1.0] to display sRGB (IEC 61966-2-1).

    Formula:
      C_srgb = 12.92 * C_linear                          for C_linear <= 0.0031308
      C_srgb = 1.055 * (C_linear ** (1.0/2.4)) - 0.055   for C_linear > 0.0031308
    """
    c_arr = np.asarray(c, dtype=np.float64)
    srgb = np.where(
        c_arr <= 0.0031308,
        12.92 * c_arr,
        1.055 * np.power(np.maximum(c_arr, 1e-12), 1.0 / 2.4) - 0.055,
    )
    return np.clip(srgb, 0.0, 1.0).astype(np.float32)


def render_preview_image(
    design: Design,
    preset: str = "corrected",
    params: Optional[OpticalSimParams] = None,
) -> Image.Image:
    """Render the optical appearance in memory, with optional scene coordinates."""
    from dot_ebl_preview.optics.presets import get_optical_preset

    if params is None:
        params = get_optical_preset(preset)
    rgb_float = render_optical_preview(design, params=params)

    # For 'corrected' preset, apply standard sRGB display transfer function to linear diffractive cells
    # Fallback intensities (if present) are already in display sRGB and must NOT be converted twice
    if preset == "corrected":
        display_rgb = np.copy(rgb_float)
        active_mask = design.active
        if np.any(active_mask):
            display_rgb[active_mask] = linear_to_srgb(rgb_float[active_mask])
        rgb_float = np.clip(display_rgb, 0.0, 1.0)
    else:
        # Legacy presets ("glsl-legacy", "unity-hsv") preserve direct ungamma-corrected shader output
        rgb_float = np.clip(rgb_float, 0.0, 1.0)

    # Convert [0, 1] float to uint8 [0, 255]
    rgb_uint8 = np.clip(np.round(rgb_float * 255.0), 0, 255).astype(np.uint8)

    return Image.fromarray(rgb_uint8, mode="RGB")


def render_preview_to_file(
    design: Design,
    output_path: Union[str, Path],
    preset: str = "corrected",
    params: Optional[OpticalSimParams] = None,
) -> Path:
    """Render the optical appearance of the design to a PNG file using the CPU engine."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    im = render_preview_image(design, preset=preset, params=params)
    im.save(p, format="PNG")
    return p


def render_angle_previews_to_directory(
    design: Design,
    output_dir: Union[str, Path],
    angles_deg: Sequence[float] = (0.0, 45.0, 90.0, 135.0),
    preset: str = "corrected",
    prefix: str = "preview_angle_az",
) -> List[Path]:
    """Render multiple optical appearance previews at varying azimuth angles to a directory.

    Args:
        design: Canonical Design instance.
        output_dir: Target directory path to write PNG images into.
        angles_deg: Sequence of azimuth angles in degrees (e.g. 0.0, 45.0, 90.0, 135.0).
        preset: Optical preset ('corrected', 'glsl-legacy', 'unity-hsv').
        prefix: Filename prefix for the angle previews.

    Returns:
        List of generated Path objects for the preview PNGs.
    """
    import dataclasses

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: List[Path] = []

    for angle in angles_deg:
        angle_float = float(angle)
        angle_int = int(round(angle_float)) if abs(angle_float - round(angle_float)) < 1e-3 else angle_float
        out_name = f"{prefix}{angle_int}.png"
        out_file = out_dir / out_name

        rotated_design = dataclasses.replace(design, angle_deg=design.angle_deg + angle_float)
        saved_path = render_preview_to_file(rotated_design, out_file, preset=preset)
        generated_paths.append(saved_path)

        # Baseline angle (0 deg) also provides standard preview.png
        if abs(angle_float) < 1e-3:
            std_preview = out_dir / "preview.png"
            if not std_preview.exists() or std_preview != saved_path:
                render_preview_to_file(rotated_design, std_preview, preset=preset)
                if std_preview not in generated_paths:
                    generated_paths.append(std_preview)

    return generated_paths
