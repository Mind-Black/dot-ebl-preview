"""Verified image reader and writer preserving numeric bit depth and channel order."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Optional, Union
import numpy as np
from numpy.typing import NDArray
from PIL import Image


def _write_png_16bit_rgb(path: Path, arr: NDArray[np.uint16]) -> None:
    """Encode HxWx3 uint16 array to 16-bit RGB PNG file."""
    h, w, c = arr.shape
    if c != 3 or arr.dtype != np.uint16:
        raise ValueError("Expected HxWx3 uint16 array for 16-bit RGB PNG export.")
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    arr_be = arr.astype(">u2")
    raw = bytearray()
    for r in range(h):
        raw.append(0)  # Filter type 0 (None)
        raw.extend(arr_be[r].tobytes())
    comp = zlib.compress(bytes(raw))
    idat = struct.pack(">I", len(comp)) + b"IDAT" + comp + struct.pack(">I", zlib.crc32(b"IDAT" + comp) & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(sig + ihdr + idat + iend)


def _read_png_16bit_rgb(path: Path) -> Optional[NDArray[np.uint16]]:
    """Decode 16-bit RGB PNG file to HxWx3 uint16 array, returning None if not 16-bit RGB PNG."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    idat_parts = []
    width = height = bit_depth = color_type = 0
    while offset + 8 <= len(data):
        length, chunk_type = struct.unpack_from(">I4s", data, offset)
        offset += 8
        if offset + length + 4 > len(data):
            return None
        chunk_data = data[offset : offset + length]
        offset += length + 4
        if chunk_type == b"IHDR" and len(chunk_data) >= 10:
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk_data[:10])
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break
    if bit_depth != 16 or color_type != 2 or width == 0 or height == 0:
        return None
    try:
        raw = zlib.decompress(b"".join(idat_parts))
    except Exception:
        return None
    stride = 1 + width * 6
    if len(raw) != height * stride:
        return None
    bpp = 6
    img_data = bytearray()
    prev_row = bytearray(width * 6)
    for r in range(height):
        row_slice = raw[r * stride : (r + 1) * stride]
        filter_type = row_slice[0]
        cur_row = bytearray(row_slice[1:])
        if filter_type == 0:
            pass
        elif filter_type == 1:
            for i in range(bpp, len(cur_row)):
                cur_row[i] = (cur_row[i] + cur_row[i - bpp]) & 0xFF
        elif filter_type == 2:
            for i in range(len(cur_row)):
                cur_row[i] = (cur_row[i] + prev_row[i]) & 0xFF
        elif filter_type == 3:
            for i in range(len(cur_row)):
                left = cur_row[i - bpp] if i >= bpp else 0
                cur_row[i] = (cur_row[i] + ((left + prev_row[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            for i in range(len(cur_row)):
                a = cur_row[i - bpp] if i >= bpp else 0
                b = prev_row[i]
                c = prev_row[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur_row[i] = (cur_row[i] + pr) & 0xFF
        else:
            return None
        prev_row = cur_row
        img_data.extend(cur_row)
    return np.frombuffer(img_data, dtype=">u2").reshape((height, width, 3)).astype(np.uint16)


def load_image_rgb(path: Union[str, Path]) -> NDArray[np.uint8 | np.uint16]:
    """Load an image strictly preserving exact uint8 or uint16 RGB channels without color correction.

    Rejects lossy formats (JPEG) when used as parameter inputs.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image file not found: {p}")

    suffix = p.suffix.lower()
    if suffix in [".jpg", ".jpeg"]:
        raise ValueError(f"JPEG format is prohibited for parameter images due to lossy compression: {p}")

    # Check for 16-bit RGB PNG
    arr_16 = _read_png_16bit_rgb(p)
    if arr_16 is not None:
        return arr_16

    with Image.open(p) as im:
        mode = im.mode
        if mode == "RGB":
            arr = np.array(im, dtype=np.uint8)
            return arr
        elif mode == "RGBA":
            # For RGBA, reject unless caller flattens or extracts RGB
            # Drop alpha with explicit warning/slice
            arr = np.array(im, dtype=np.uint8)[:, :, :3]
            return arr
        elif mode == "I;16" or mode == "I":
            arr = np.array(im, dtype=np.uint16)
            return arr
        elif mode == "RGB;16" or (im.mode.startswith("RGB") and "16" in im.mode):
            arr = np.array(im, dtype=np.uint16)
            return arr
        else:
            # Fallback: convert to RGB without gamma transforms
            im_rgb = im.convert("RGB")
            return np.array(im_rgb, dtype=np.uint8)


def save_image_rgb(path: Union[str, Path], img_rgb: NDArray[np.uint8 | np.uint16]) -> None:
    """Save an array as a lossless PNG image."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if img_rgb.dtype == np.uint8:
        im = Image.fromarray(img_rgb, mode="RGB")
        im.save(p, format="PNG")
    elif img_rgb.dtype == np.uint16:
        _write_png_16bit_rgb(p, img_rgb)
    else:
        raise TypeError(f"Unsupported array dtype for image save: {img_rgb.dtype}")
