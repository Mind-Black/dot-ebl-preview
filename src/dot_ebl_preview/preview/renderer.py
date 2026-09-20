"""Optical preview renderer with headless CPU mode and optional OpenGL support."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union
import numpy as np
from PIL import Image

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.optics.engine import OpticalSimParams, render_optical_preview


def render_preview_to_file(
    design: Design,
    output_path: Union[str, Path],
    preset: str = "corrected",
) -> Path:
    """Render the optical appearance of the design to a PNG file using the CPU engine."""
    from dot_ebl_preview.optics.presets import get_optical_preset

    params = get_optical_preset(preset)
    rgb_float = render_optical_preview(design, params=params)

    # Convert [0, 1] float to uint8 [0, 255]
    rgb_uint8 = np.clip(np.round(rgb_float * 255.0), 0, 255).astype(np.uint8)

    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    im = Image.fromarray(rgb_uint8, mode="RGB")
    im.save(p, format="PNG")
    return p
