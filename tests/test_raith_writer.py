"""Tests for pure-Python Raith GDSII binary serializer and record roundtrip."""

import io
import struct
import pytest
from pathlib import Path

from dot_ebl_preview.raith.elements import PathElement, SrefElement
from dot_ebl_preview.raith.library import RaithLibrary
from dot_ebl_preview.raith.records import (
    df_to_datatype,
    excess64_decode,
    excess64_encode,
    pack_gds_record,
)
from dot_ebl_preview.raith.structures import RaithStructure
from dot_ebl_preview.raith.writer import write_gds_stream


def test_excess64_roundtrip():
    test_values = [
        0.0,
        1.0,
        -1.0,
        1e-3,
        1e-9,
        45.0,
        -90.0,
        12.34567,
        1328.0,
        0.001,
    ]
    for val in test_values:
        encoded = excess64_encode(val)
        assert len(encoded) == 8
        decoded = excess64_decode(encoded)
        if val == 0.0:
            assert decoded == 0.0
        else:
            rel_err = abs(decoded - val) / abs(val)
            assert rel_err < 1e-12, f"excess64 roundtrip error too large for {val}: got {decoded}"


def test_df_to_datatype():
    # DF <= 30 -> 1000 * DF
    assert df_to_datatype(1.0) == 1000
    assert df_to_datatype(1.5) == 1500
    assert df_to_datatype(30.0) == 30000
    # DF > 30 -> 30000 + 2 * (DF - 30)
    assert df_to_datatype(31.0) == 30002
    assert df_to_datatype(40.0) == 30020


def test_hierarchy_cycle_detection():
    lib = RaithLibrary(name="CYCLE_TEST")
    s1 = RaithStructure(name="S1")
    s2 = RaithStructure(name="S2")

    # S1 references S2, S2 references S1 -> cycle!
    s1.add_element(SrefElement(name="S2", origin_nm=(0, 0)))
    s2.add_element(SrefElement(name="S1", origin_nm=(0, 0)))

    lib.add_structure(s1)
    lib.add_structure(s2)

    with pytest.raises(ValueError, match="Reference cycle detected"):
        lib.validate_hierarchy()


def test_independent_gds_record_readback(tmp_path: Path):
    """Serialize a test library and parse the raw binary records byte-by-byte."""
    lib = RaithLibrary(name="TEST_LIB")

    # Cell structure
    cell = RaithStructure(name="CELL_1")
    cell.add_element(
        PathElement(
            layer=1,
            vertices_nm=[(-5000, 0), (5000, 0)],
            width_nm=0,
            df=1.0,
        )
    )
    lib.add_structure(cell)

    # Top structure
    top = RaithStructure(name="TOP")
    top.add_element(
        SrefElement(
            name="CELL_1",
            origin_nm=(10000, -10000),
            angle_deg=45.0,
        )
    )
    lib.add_structure(top)

    out_file = tmp_path / "test.gds"
    lib.write_gds(out_file)
    assert out_file.exists()

    # Parse GDSII records independently
    with open(out_file, "rb") as f:
        data = f.read()

    offset = 0
    records = []
    while offset < len(data):
        rec_len, rectype, datatype = struct.unpack_from(">HBB", data, offset)
        assert rec_len >= 4
        assert rec_len % 2 == 0  # Even padding
        payload = data[offset + 4 : offset + rec_len]
        records.append((rectype, datatype, payload))
        offset += rec_len

    rectypes = [r[0] for r in records]

    # Verify key GDS record types sequence
    # HEADER(0), BGNLIB(1), LIBNAME(2), UNITS(3),
    # BGNSTR(5), STRNAME(6), PATH(9), LAYER(13), DATATYPE(14), WIDTH(15), XY(16), ENDEL(17), ENDSTR(7),
    # BGNSTR(5), STRNAME(6), SREF(10), SNAME(18), STRANS(26), MAG(27), ANGLE(28), XY(16), ENDEL(17), ENDSTR(7),
    # ENDLIB(4)
    assert rectypes[0] == 0   # HEADER
    assert rectypes[1] == 1   # BGNLIB
    assert rectypes[2] == 2   # LIBNAME
    assert rectypes[3] == 3   # UNITS
    assert 9 in rectypes      # PATH
    assert 15 in rectypes     # WIDTH
    assert 10 in rectypes     # SREF
    assert rectypes[-1] == 4  # ENDLIB

    # Verify that WIDTH is explicitly zero (4 bytes int32)
    width_record = [r for r in records if r[0] == 15][0]
    width_val = struct.unpack(">i", width_record[2][:4])[0]
    assert width_val == 0
