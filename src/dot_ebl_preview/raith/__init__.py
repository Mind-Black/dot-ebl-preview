"""Raith GDSII serializer and object model."""

from dot_ebl_preview.raith.records import (
    excess64_encode,
    excess64_decode,
    df_to_datatype,
    pack_gds_record,
)
from dot_ebl_preview.raith.elements import (
    PathElement,
    SrefElement,
    sanitize_structure_name,
)
from dot_ebl_preview.raith.structures import RaithStructure
from dot_ebl_preview.raith.library import RaithLibrary
from dot_ebl_preview.raith.writer import write_gds_stream
from dot_ebl_preview.raith.capabilities import (
    check_element_capability,
    require_element_capability,
    DEFERRED_FEATURES,
)

__all__ = [
    "excess64_encode",
    "excess64_decode",
    "df_to_datatype",
    "pack_gds_record",
    "PathElement",
    "SrefElement",
    "sanitize_structure_name",
    "RaithStructure",
    "RaithLibrary",
    "write_gds_stream",
    "check_element_capability",
    "require_element_capability",
    "DEFERRED_FEATURES",
]
