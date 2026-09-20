"""Pure-Python GDSII binary serializer matching Raith_library.m specifications.

Notes on Deferred Raith Writer Features (per docs/DEVELOPMENT_PLAN.md & docs/RAITH_PORT.md):
  TODO(Raith): Native Raith CSF (.csf) binary format export.
  Raith_library.m supports writing native Compound Structure Files (.csf) with Raith-specific
  binary headers and layer definitions. Deferred pending qualification on a physical Raith
  system running NanoSuite to verify header interpretations and coordinate scaling.

  TODO(Raith): AREF (Array Reference) record generation (record type 11 / AREF).
  TODO(Raith): Native curved elements (record type 86) for arcs, circles, and ellipses.
  TODO(Raith): Fixed Beam Moving Stage (record type 88 / FBMS) path/circle elements.
"""

from __future__ import annotations

import datetime
from typing import BinaryIO, List
import numpy as np

from dot_ebl_preview.raith.elements import PathElement, SrefElement
from dot_ebl_preview.raith.library import RaithLibrary
from dot_ebl_preview.raith.records import df_to_datatype, pack_gds_record


def _current_gds_timestamps() -> List[int]:
    """Generate 12-integer timestamp array [Y, M, D, h, m, s, Y, M, D, h, m, s]."""
    now = datetime.datetime.now()
    d = [now.year, now.month, now.day, now.hour, now.minute, now.second]
    return d + d


def write_gds_stream(lib: RaithLibrary, stream: BinaryIO) -> None:
    """Serialize a RaithLibrary to an open binary stream in pure Python.

    Emits standard GDSII stream format release 3 with big-endian record headers
    and Raith single-pixel path / SREF elements:
      - HEADER (rectype 0, version 3)
      - BGNLIB (rectype 1, timestamps)
      - LIBNAME (rectype 2)
      - UNITS (rectype 3: user_unit 1e-3, db_unit 1e-9)
      - STRUCTURES with PATH (width=0 nm, DATATYPE=DFint) and SREF (STRANS, MAG, ANGLE, XY)
      - ENDLIB (rectype 4)

    Args:
        lib: RaithLibrary instance containing named structures and elements.
        stream: Writable binary file-like object.
    """
    timestamps = _current_gds_timestamps()

    # 1. HEADER (rectype 0, datatype 2): release version 3
    stream.write(pack_gds_record(0, 2, [3]))

    # 2. BGNLIB (rectype 1, datatype 2): timestamps
    stream.write(pack_gds_record(1, 2, timestamps))

    # 3. LIBNAME (rectype 2, datatype 6): library name
    stream.write(pack_gds_record(2, 6, lib.name))

    # 4. UNITS (rectype 3, datatype 5): [user_unit in meters, db_unit in meters]
    stream.write(pack_gds_record(3, 5, [lib.user_unit_m, lib.database_unit_m]))

    # 5. Write each structure
    for sname, struct_obj in lib.structures.items():
        # BGNSTR (rectype 5, datatype 2)
        stream.write(pack_gds_record(5, 2, timestamps))
        # STRNAME (rectype 6, datatype 6)
        stream.write(pack_gds_record(6, 6, struct_obj.name))

        # Write elements
        for el in struct_obj.elements:
            if isinstance(el, PathElement):
                # PATH (rectype 9, datatype 0)
                stream.write(pack_gds_record(9, 0))
                # LAYER (rectype 13, datatype 2)
                stream.write(pack_gds_record(13, 2, [el.layer]))
                # DATATYPE (rectype 14, datatype 2): DF encoded as integer
                df_int = df_to_datatype(el.df)
                stream.write(pack_gds_record(14, 2, [df_int]))
                # WIDTH (rectype 15, datatype 3): in nm, 0 for single-pixel line
                stream.write(pack_gds_record(15, 3, [el.width_nm]))
                # XY (rectype 16, datatype 3): 1D array of int32 sequential XY pairs (in nm)
                xy_flat = []
                for vx, vy in el.vertices_nm:
                    xy_flat.extend([int(vx), int(vy)])
                stream.write(pack_gds_record(16, 3, xy_flat))
                # ENDEL (rectype 17, datatype 0)
                stream.write(pack_gds_record(17, 0))

            elif isinstance(el, SrefElement):
                # SREF (rectype 10, datatype 0)
                stream.write(pack_gds_record(10, 0))
                # SNAME (rectype 18, datatype 6)
                stream.write(pack_gds_record(18, 6, el.name))

                # Transform flags (STRANS)
                if el.reflect:
                    stream.write(pack_gds_record(26, 1, [32768]))  # Reflect in X
                if el.mag != 1.0 or el.angle_deg != 0.0:
                    if not el.reflect:
                        stream.write(pack_gds_record(26, 1, [0]))
                    stream.write(pack_gds_record(27, 5, [el.mag]))        # MAG (rectype 27, datatype 5)
                    stream.write(pack_gds_record(28, 5, [el.angle_deg]))  # ANGLE (rectype 28, datatype 5)

                # XY (rectype 16, datatype 3): origin in nm
                ox, oy = el.origin_nm
                stream.write(pack_gds_record(16, 3, [int(ox), int(oy)]))
                # ENDEL (rectype 17, datatype 0)
                stream.write(pack_gds_record(17, 0))
            else:
                raise TypeError(f"Unsupported Raith element type: {type(el)}")

        # ENDSTR (rectype 7, datatype 0)
        stream.write(pack_gds_record(7, 0))

    # 6. ENDLIB (rectype 4, datatype 0)
    stream.write(pack_gds_record(4, 0))
