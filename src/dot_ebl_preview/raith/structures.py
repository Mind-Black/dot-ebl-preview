"""Named GDSII structures and hierarchy validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set, Union

from dot_ebl_preview.raith.elements import PathElement, SrefElement, sanitize_structure_name


RaithElement = Union[PathElement, SrefElement]


@dataclass
class RaithStructure:
    """Named GDSII structure containing elements."""
    name: str
    elements: List[RaithElement] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = sanitize_structure_name(self.name)

    def add_element(self, element: RaithElement) -> None:
        self.elements.append(element)

    def referenced_structures(self) -> Set[str]:
        """Return the set of structure names referenced by SREF elements."""
        refs: Set[str] = set()
        for el in self.elements:
            if isinstance(el, SrefElement):
                refs.add(el.name)
        return refs
