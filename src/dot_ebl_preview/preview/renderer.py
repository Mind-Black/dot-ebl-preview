"""Optical preview renderer with headless CPU mode and optional OpenGL support."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union
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


def render_preview_to_file(
    design: Design,
    output_path: Union[str, Path],
    preset: str = "corrected",
) -> Path:
    """Render the optical appearance of the design to a PNG file using the CPU engine."""
    from dot_ebl_preview.optics.presets import get_optical_preset

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

    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    im = Image.fromarray(rgb_uint8, mode="RGB")
    im.save(p, format="PNG")
    return p
