"""FabricationPlan dataclass and layout derivation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict
import numpy as np

from dot_ebl_preview.core.grid import Extents, design_extents_nm
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.layout.placements import build_hologram_layout
from dot_ebl_preview.raith.library import RaithLibrary


@dataclass(frozen=True)
class FabricationPlan:
    """Derived fabrication plan consumed by geometry preview and Raith export."""
    design_hash: str
    top_structure_name: str
    library: RaithLibrary
    holopixel_structures: Dict[int, str]
    total_cells: int
    active_cells: int
    total_stripes: int
    skipped_degenerate_stripes: int
    unique_periods_count: int
    extents: Extents
    plan_hash: str


def create_fabrication_plan(design: Design, top_name: str = "HOLOGRAM") -> FabricationPlan:
    """Build immutable FabricationPlan from authoritative Design."""
    h, w = design.shape
    total_cells = h * w
    active_cells = design.active_count

    lib, struct_map, total_stripes, total_skipped = build_hologram_layout(design, top_name=top_name)
    extents = design_extents_nm(h, w, design.pitch_nm)
    des_hash = design.content_hash()

    hasher = hashlib.sha256()
    hasher.update(des_hash.encode())
    hasher.update(top_name.encode())
    hasher.update(f"stripes:{total_stripes}:skipped:{total_skipped}".encode())
    plan_hash = hasher.hexdigest()

    return FabricationPlan(
        design_hash=des_hash,
        top_structure_name=top_name,
        library=lib,
        holopixel_structures=struct_map,
        total_cells=total_cells,
        active_cells=active_cells,
        total_stripes=total_stripes,
        skipped_degenerate_stripes=total_skipped,
        unique_periods_count=len(struct_map),
        extents=extents,
        plan_hash=plan_hash,
    )
