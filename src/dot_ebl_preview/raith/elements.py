"""Raith GDSII elements: Path (width 0 single-pixel line) and SREF (structure reference)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple
import numpy as np


def sanitize_structure_name(name: str, max_len: int = 32) -> str:
    """Sanitize structure name to conservative valid ASCII (letters, digits, underscores, dashes).

    Truncates to max_len (default 32 characters for maximum portability).
    """
    if max_len <= 0:
        max_len = 32
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    cleaned = cleaned[:max_len]
    if not cleaned:
        cleaned = "unnamed"
    return cleaned


@dataclass
class PathElement:
    """Raith single-pixel line path element (width 0).

    In Raith EBL:
      - width_nm = 0 represents a single-pixel line exposure.
      - vertices_nm: sequence of (x, y) integer nanometres.
      - layer: integer between 0 and 63.
      - df: dose factor (non-negative, <= 17797.5).
    """
    layer: int
    vertices_nm: List[Tuple[int, int]]
    width_nm: int = 0
    df: float = 1.0

    def __post_init__(self) -> None:
        if not (0 <= self.layer <= 63):
            raise ValueError(f"Path layer must be 0..63, got {self.layer}")
        if self.width_nm != 0:
            raise ValueError(f"Single-pixel line path must have width_nm == 0, got {self.width_nm}")
        if len(self.vertices_nm) < 2:
            raise ValueError(f"Path must contain at least 2 vertices, got {len(self.vertices_nm)}")
        if not np.isfinite(self.df) or self.df < 0.0 or self.df > 17797.5:
            raise ValueError(f"Dose factor must be a finite number in [0, 17797.5], got {self.df}")
        # Validate vertices are integer coordinates and not degenerate
        for x, y in self.vertices_nm:
            if not isinstance(x, (int, np.integer)) or not isinstance(y, (int, np.integer)):
                raise TypeError(f"Path coordinates must be integer nm, got ({type(x)}, {type(y)})")
            if not (-2147483648 <= int(x) <= 2147483647 and -2147483648 <= int(y) <= 2147483647):
                raise ValueError(f"Path coordinate out of 32-bit signed range: ({x}, {y})")


@dataclass
class SrefElement:
    """Structure reference (SREF) element with rotation and translation.

    In Raith EBL:
      - name: referenced structure name (sanitized).
      - origin_nm: (x, y) in integer nanometres.
      - angle_deg: rotation angle in degrees (CCW).
      - mag: magnification (positive float, default 1.0).
      - reflect: reflection in X axis (default False).
    """
    name: str
    origin_nm: Tuple[int, int]
    angle_deg: float = 0.0
    mag: float = 1.0
    reflect: bool = False

    def __post_init__(self) -> None:
        self.name = sanitize_structure_name(self.name)
        if not np.isfinite(self.mag) or self.mag <= 0:
            raise ValueError(f"SREF magnification must be positive finite number, got {self.mag}")
        x, y = self.origin_nm
        if not isinstance(x, (int, np.integer)) or not isinstance(y, (int, np.integer)):
            raise TypeError(f"SREF origin must be integer nm, got ({type(x)}, {type(y)})")
        if not (-2147483648 <= int(x) <= 2147483647 and -2147483648 <= int(y) <= 2147483647):
            raise ValueError(f"SREF origin coordinate out of 32-bit signed range: ({x}, {y})")
        if not np.isfinite(self.angle_deg):
            raise ValueError("SREF angle must be finite.")


# =====================================================================
# Deferred Raith Elements (Inventory per DEVELOPMENT_PLAN.md & RAITH_PORT.md)
# =====================================================================

from dot_ebl_preview.raith.capabilities import require_element_capability


@dataclass
class ArefElement:
    """TODO(Raith): 2D array reference (AREF, record type 11).

    Upstream: Raith_element.m:481, Raith_library.m:writeelement.
    Deferred in MVP; requires COLROW stepping vectors and verification of Raith rotation/reflection
    semantics versus standard GDSII readers before enabling regular grid compression.
    """
    name: str = ""

    def __post_init__(self) -> None:
        require_element_capability("aref")


@dataclass
class ArcElement:
    """TODO(Raith): Curved arc/disc segment (record type 86).

    Upstream: Raith_element.m:arc, Raith_library.m:writerec.
    Deferred in MVP; requires native curved record serialization, angular span parameters,
    and fallback chord polygonal tessellation for generic GDS readers.
    """
    def __post_init__(self) -> None:
        require_element_capability("arc")


@dataclass
class CircleElement:
    """TODO(Raith): Curved circle element (record type 86).

    Upstream: Raith_element.m:circle, Raith_library.m:writerec.
    Deferred in MVP; requires native curved record generation or polygonal chord approximation.
    """
    def __post_init__(self) -> None:
        require_element_capability("circle")


@dataclass
class EllipseElement:
    """TODO(Raith): Curved ellipse element (record type 86).

    Upstream: Raith_element.m:ellipse, Raith_library.m:writerec.
    Deferred in MVP; requires major/minor axes handling, center offset, and rotation angle.
    """
    def __post_init__(self) -> None:
        require_element_capability("ellipse")


@dataclass
class TextElement:
    """TODO(Raith): Polygonized font glyph rendering.

    Upstream: Raith_element.m:rendertext.
    Deferred in MVP; requires embedded character font tables, proper kerning/alignment,
    and vector path generation without replacing with non-standard GDSII text elements.
    """
    def __post_init__(self) -> None:
        require_element_capability("text")


@dataclass
class FBMSPathElement:
    """TODO(Raith): Fixed Beam Moving Stage path (record type 88).

    Upstream: Raith_element.m:fbmspath.
    Deferred in MVP; requires continuous stage velocity control flags and line dose
    conversion for stitch-free extended waveguides.
    """
    def __post_init__(self) -> None:
        require_element_capability("fbmspath")


@dataclass
class FBMSCircleElement:
    """TODO(Raith): Fixed Beam Moving Stage circle (record type 88).

    Upstream: Raith_element.m:fbmscircle.
    Deferred in MVP; requires FBMS circle records and stage coordinate offsets.
    """
    def __post_init__(self) -> None:
        require_element_capability("fbmscircle")

