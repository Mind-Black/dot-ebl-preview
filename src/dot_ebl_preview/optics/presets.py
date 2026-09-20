"""Optical simulation named presets."""

from __future__ import annotations

from typing import Dict
from dot_ebl_preview.optics.engine import OpticalSimParams


PRESETS: Dict[str, OpticalSimParams] = {
    "corrected": OpticalSimParams(
        orders=(-1, 1),
        include_order_2=False,
        unity_mode=False,
    ),
    "glsl-legacy": OpticalSimParams(
        orders=(-1, 1),
        include_order_2=False,
        unity_mode=False,
    ),
    "unity-hsv": OpticalSimParams(
        orders=(-2, -1, 1, 2),
        include_order_2=True,
        order_2_weight=1.0 / 15.0,
        unity_mode=True,
    ),
}


def get_optical_preset(name: str) -> OpticalSimParams:
    if name not in PRESETS:
        raise ValueError(f"Unknown optical preset: '{name}'. Available: {list(PRESETS.keys())}")
    return PRESETS[name]
