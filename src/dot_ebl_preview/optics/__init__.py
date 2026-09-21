"""Optical simulation engine, tables, and presets."""

from dot_ebl_preview.optics.tables import (
    XYZ2RGB,
    s2xyz,
    specIntens,
    stdIllum,
    reflNi,
    redxyY,
    greenxyY,
    bluexyY,
    period_real,
    laser_hues,
    premultiplied_XYZ,
)
from dot_ebl_preview.optics.engine import (
    LightSource,
    OpticalSimParams,
    simulate_cell_optical_color,
    render_optical_preview,
)
from dot_ebl_preview.optics.presets import PRESETS, get_optical_preset

__all__ = [
    "XYZ2RGB",
    "s2xyz",
    "specIntens",
    "stdIllum",
    "reflNi",
    "redxyY",
    "greenxyY",
    "bluexyY",
    "period_real",
    "laser_hues",
    "premultiplied_XYZ",
    "LightSource",
    "OpticalSimParams",
    "simulate_cell_optical_color",
    "render_optical_preview",
    "PRESETS",
    "get_optical_preset",
]
