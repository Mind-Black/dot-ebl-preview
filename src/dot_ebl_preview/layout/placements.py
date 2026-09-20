"""Hologram reference placement and structure hierarchy construction."""

from __future__ import annotations

from typing import Dict, List, Tuple
import numpy as np

from dot_ebl_preview.core.grid import cell_center_nm
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.layout.holopixel import generate_holopixel_stripes
from dot_ebl_preview.raith.elements import SrefElement, sanitize_structure_name
from dot_ebl_preview.raith.library import RaithLibrary
from dot_ebl_preview.raith.structures import RaithStructure


def build_hologram_layout(
    design: Design,
    top_name: str = "HOLOGRAM",
) -> Tuple[RaithLibrary, Dict[int, str], int, int]:
    """Build complete RaithLibrary hierarchy for the Design.

    Returns:
      (library, period_structure_map, total_stripes, total_skipped_stripes)
    """
    clean_top_name = sanitize_structure_name(top_name)
    lib = RaithLibrary(name=clean_top_name + "_LIB")

    h, w = design.shape
    active = design.active

    if not np.any(active):
        # Empty hologram handling
        top_struct = RaithStructure(name=clean_top_name)
        lib.add_structure(top_struct)
        return lib, {}, 0, 0

    active_periods = np.unique(design.period_nm[active])

    period_struct_map: Dict[int, str] = {}
    total_stripes = 0
    total_skipped = 0

    # 1. Create unique holopixel cell structures
    for period in active_periods:
        sname = sanitize_structure_name(f"P_{period}")
        period_struct_map[int(period)] = sname

        paths, skipped = generate_holopixel_stripes(
            pitch_nm=design.pitch_nm,
            period_nm=int(period),
            layer=design.layer,
            dose=design.dose,
        )
        total_stripes += len(paths)
        total_skipped += skipped

        cell_struct = RaithStructure(name=sname, elements=list(paths))
        lib.add_structure(cell_struct)

    # 2. Create top hologram structure with SREF placements
    top_struct = RaithStructure(name=clean_top_name)

    active_rows, active_cols = np.nonzero(active)
    for r, c in zip(active_rows, active_cols):
        p = int(design.period_nm[r, c])
        rot = float(design.angle_deg[r, c])
        cell_name = period_struct_map[p]

        ox, oy = cell_center_nm(int(r), int(c), design.pitch_nm)
        sref = SrefElement(
            name=cell_name,
            origin_nm=(ox, oy),
            angle_deg=rot,
        )
        top_struct.add_element(sref)

    lib.add_structure(top_struct)
    lib.validate_hierarchy()

    return lib, period_struct_map, total_stripes, total_skipped
