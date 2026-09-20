"""Raith capabilities registry and deferred features inventory."""

from __future__ import annotations

from typing import Dict, List, Set


SUPPORTED_ELEMENTS: Set[str] = {"path_single_pixel", "sref"}
SUPPORTED_DIALECTS: Set[str] = {"gdsii_plain", "raith_line_gds"}

DEFERRED_FEATURES: Dict[str, str] = {
    "polygon": (
        "TODO(Raith): Filled polygon closure and area-dose conversion (Raith_element.m:221). "
        "Deferred in MVP because dot-ebl-preview standardizes exclusively on zero-width single-pixel line exposure."
    ),
    "path_finite_width": (
        "TODO(Raith): Paths with non-zero line width and polylines with >2 vertices (Raith_element.m:305). "
        "Deferred in MVP; requires finite width handling, endpoint cap extensions, and area/line dose disambiguation."
    ),
    "aref": (
        "TODO(Raith): 2D array references (AREF, record type 11) and regular lattice compression (Raith_element.m:481, "
        "Raith_library.m:writeelement). Requires COLROW stepping vectors and verification of Raith rotation/reflection "
        "semantics versus standard GDSII readers before enabling regular grid compression."
    ),
    "arc": (
        "TODO(Raith): Raith curved disc segment (record type 86, Raith_element.m:arc). Requires native curved record "
        "serialization, angular span parameters, and fallback chord polygonal tessellation for generic GDS readers."
    ),
    "circle": (
        "TODO(Raith): Raith curved circle element (record type 86, Raith_element.m:circle). Requires native curved record "
        "generation or polygonal chord approximation."
    ),
    "ellipse": (
        "TODO(Raith): Raith curved ellipse element (record type 86, Raith_element.m:ellipse). Requires major/minor axes "
        "handling, center offset, and rotation angle."
    ),
    "text": (
        "TODO(Raith): Polygonized font glyph rendering (Raith_element.m:rendertext). Requires embedded character font tables, "
        "proper kerning/alignment, and vector path generation without replacing with non-standard GDSII text elements."
    ),
    "fbmspath": (
        "TODO(Raith): Raith Fixed Beam Moving Stage path (record type 88, Raith_element.m:fbmspath). Requires continuous "
        "stage velocity control flags and line dose conversion for stitch-free extended waveguides."
    ),
    "fbmscircle": (
        "TODO(Raith): Raith Fixed Beam Moving Stage circle (record type 88, Raith_element.m:fbmscircle). Requires FBMS circle "
        "records and stage coordinate offsets."
    ),
    "positionlist": (
        "TODO(Raith): Raith position list (.pls) export (Raith_positionlist.m). Requires stage coordinate translation, "
        "working area (WA) and writefield (WF) unit conversions (mm vs µm), and multi-chip origin lists."
    ),
    "csf": (
        "TODO(Raith): Native Raith Compound Structure File (.csf) binary format. Deferred pending qualification against an "
        "actual physical Raith NanoSuite installation to verify layer, line-mode, and dose interpretation."
    ),
}


def check_element_capability(element_type: str) -> bool:
    """Check if a Raith element type is supported in the current version.

    Args:
        element_type: Element type string (e.g. 'path_single_pixel', 'sref', 'aref', 'arc').

    Returns:
        bool: True if supported and can be serialized to GDSII, False if deferred or unknown.
    """
    return element_type in SUPPORTED_ELEMENTS


def require_element_capability(element_type: str) -> None:
    """Assert that a Raith element type is supported; raise NotImplementedError if deferred.

    Args:
        element_type: Element type string.

    Raises:
        NotImplementedError: If the element is deferred or not yet ported, with a descriptive TODO.
    """
    if element_type not in SUPPORTED_ELEMENTS:
        reason = DEFERRED_FEATURES.get(element_type, "Unrecognized or unported Raith feature.")
        raise NotImplementedError(f"Raith element '{element_type}' is not supported in MVP. {reason}")
