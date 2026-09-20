"""Raith GDSII Library container and hierarchy verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple, Union

from dot_ebl_preview.raith.elements import sanitize_structure_name
from dot_ebl_preview.raith.structures import RaithStructure


@dataclass
class RaithLibrary:
    """GDSII Library containing ordered structures.

    Units:
      - user_unit: 1e-3 (1 µm in metres)
      - db_unit: 1e-9 (1 nm in metres)
    """
    name: str = "RAITH_LIB"
    user_unit_m: float = 1e-3
    database_unit_m: float = 1e-9
    structures: Dict[str, RaithStructure] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = sanitize_structure_name(self.name)

    def add_structure(self, structure: RaithStructure) -> None:
        if structure.name in self.structures:
            raise ValueError(f"Structure '{structure.name}' already exists in library.")
        self.structures[structure.name] = structure

    def validate_hierarchy(self) -> None:
        """Validate that all referenced structures exist and there are no reference cycles."""
        all_names = set(self.structures.keys())

        # Check missing references
        for sname, struct_obj in self.structures.items():
            refs = struct_obj.referenced_structures()
            missing = refs - all_names
            if missing:
                raise ValueError(f"Structure '{sname}' references missing structures: {missing}")

        # Check cycle detection via DFS
        visited: Dict[str, int] = {}  # 0: visiting, 1: visited

        def dfs(node: str, path: List[str]) -> None:
            visited[node] = 0
            for neighbor in self.structures[node].referenced_structures():
                if neighbor not in visited:
                    dfs(neighbor, path + [neighbor])
                elif visited[neighbor] == 0:
                    cycle_path = " -> ".join(path + [neighbor])
                    raise ValueError(f"Reference cycle detected in GDS hierarchy: {cycle_path}")
            visited[node] = 1

        for name in all_names:
            if name not in visited:
                dfs(name, [name])

    def write_gds(self, path: Union[str, Path]) -> Path:
        """Serialize library to binary GDSII file."""
        from dot_ebl_preview.raith.writer import write_gds_stream
        self.validate_hierarchy()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            write_gds_stream(self, f)
        return p
