"""GDSII low-level binary records, excess-64 real8 encoding, and DFint dose mapping."""

from __future__ import annotations

import math
import struct
from typing import List, Sequence, Union
import numpy as np

from dot_ebl_preview.core.encoding import round_half_away_from_zero


def excess64_encode(num: float) -> bytes:
    """Convert floating-point number to GDSII 8-byte excess-64 format.

    Port of Raith_library.m excess64 function based on Ulf Griesmann's gdsii_excess64enc.c.
    Returns 8 bytes:
      Byte 0: Sign bit (bit 7) and 7-bit base-16 exponent (bits 0-6, excess-64).
      Bytes 1-7: 56-bit mantissa (base-16 fraction in [1/16, 1)).
    """
    if num == 0.0 or num == -0.0:
        return b"\x00" * 8

    if math.isnan(num) or math.isinf(num):
        raise ValueError(f"Cannot encode non-finite number in GDS excess-64: {num}")

    if num < 0:
        sgn = -1
        n = -num
    else:
        sgn = 1
        n = num

    # frexp returns (m, e) where n = m * 2^e and 0.5 <= |m| < 1
    mn, ex = math.frexp(n)
    ex16 = ex / 4.0
    E = int(math.ceil(ex16))
    # Base 16 mantissa: mn * 16^(ex16 - E)
    M = mn * (16.0 ** (ex16 - E))

    # Normalize representation such that 1/16 <= M < 1
    while M >= 1.0:
        M /= 16.0
        E += 1

    while M < (1.0 / 16.0):
        M *= 16.0
        E -= 1

    E += 64  # Excess-64 exponent
    if E < 0 or E > 127:
        raise OverflowError(f"Exponent out of GDS real8 bounds: E={E} for num={num}")
    if sgn < 0:
        E |= 128  # Leading sign bit

    # Extract 7 bytes of mantissa
    b = bytearray(7)
    for k in range(7):
        M *= 256.0
        int_part = min(255, max(0, int(math.floor(M))))
        b[k] = int_part & 0xFF
        M -= int_part

    return bytes([E]) + bytes(b)


def excess64_decode(data: bytes) -> float:
    """Decode an 8-byte GDSII excess-64 float to standard float64."""
    if len(data) != 8:
        raise ValueError(f"excess-64 float requires 8 bytes, got {len(data)}")
    if data == b"\x00" * 8:
        return 0.0

    b0 = data[0]
    sgn = -1.0 if (b0 & 0x80) else 1.0
    E = (b0 & 0x7F) - 64

    # Mantissa from next 7 bytes
    mantissa = 0.0
    factor = 1.0 / 256.0
    for byte_val in data[1:8]:
        mantissa += byte_val * factor
        factor /= 256.0

    return sgn * mantissa * (16.0 ** E)


def df_to_datatype(df: float) -> int:
    """Convert dose factor (DF) to GDSII integer DATATYPE.

    Upstream Raith_library.m:DFint:
      DF <= 30 -> 1000 * DF (precision 0.001)
      DF > 30  -> 30000 + 2 * (DF - 30) (precision 0.5)
    """
    if not math.isfinite(df) or df < 0:
        raise ValueError(f"Dose factor must be non-negative finite number, got {df}")
    if df > 17797.5:
        raise ValueError(f"Dose factor must not exceed 17797.5, got {df}")

    if df <= 30.0:
        # 0.001 precision
        val = round_half_away_from_zero(df * 1000.0)
    else:
        # 0.5 precision
        rounded_df = round_half_away_from_zero(df * 2.0) / 2.0
        val = round_half_away_from_zero(30000.0 + 2.0 * (rounded_df - 30.0))

    return int(val)


def pack_gds_record(rectype: int, datatype: int, payload: Union[bytes, Sequence[int], Sequence[float], str] = b"") -> bytes:
    """Pack a GDSII binary record with big-endian header and even-byte padding.

    Header (4 bytes):
      - 2 bytes: Total record length (header + payload + pad)
      - 1 byte:  Record type (rectype)
      - 1 byte:  Data type (datatype)
    """
    # Datatypes:
    # 0: no data
    # 1: 2-byte integer bit-array (uint16)
    # 2: 2-byte signed integer (int16 / uint16)
    # 3: 4-byte signed integer (int32)
    # 5: 8-byte float (excess-64)
    # 6: ASCII character string
    body = bytearray()

    if datatype == 0:
        pass
    elif datatype == 1 or datatype == 2:
        if isinstance(payload, (int, np.integer)):
            body.extend(struct.pack(">H", int(payload) & 0xFFFF))
        else:
            for item in payload:
                body.extend(struct.pack(">H", int(item) & 0xFFFF))
    elif datatype == 3:
        if isinstance(payload, (int, np.integer)):
            body.extend(struct.pack(">i", int(payload)))
        else:
            for item in payload:
                body.extend(struct.pack(">i", int(item)))
    elif datatype == 5:
        if isinstance(payload, (int, float, np.floating, np.integer)):
            body.extend(excess64_encode(float(payload)))
        else:
            for item in payload:
                body.extend(excess64_encode(float(item)))
    elif datatype == 6:
        if isinstance(payload, str):
            body.extend(payload.encode("ascii"))
        else:
            body.extend(bytes(payload))
    else:
        raise ValueError(f"Unknown GDS datatype: {datatype}")

    # Odd length padding
    if len(body) % 2 == 1:
        body.append(0)

    total_len = len(body) + 4
    if total_len > 65534:
        raise ValueError(f"Record length {total_len} exceeds GDS maximum 65534 bytes.")

    header = struct.pack(">HBB", total_len, rectype, datatype)
    return header + body
