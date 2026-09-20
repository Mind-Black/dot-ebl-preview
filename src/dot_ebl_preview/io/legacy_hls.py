"""Legacy OpenCV HLS importer (Holtida-EBL and learning-shaders compatibility)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Tuple, Union
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from dot_ebl_preview.core.model import Design, OperationRecord
from dot_ebl_preview.core.encoding import round_half_away_from_zero
from dot_ebl_preview.core.operations import apply_radial_gradient


def rgb_to_opencv_hls(img_rgb: NDArray[np.uint8]) -> Tuple[NDArray[np.uint8], NDArray[np.uint8], NDArray[np.uint8]]:
    """Convert uint8 RGB image to OpenCV HLS channels (H in 0..179, L in 0..255, S in 0..255).

    Uses cv2 if available, otherwise exact pure-numpy vectorized implementation.
    """
    try:
        import cv2
        # cv2 expects BGR
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        img_hls = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HLS)
        h, l, s = cv2.split(img_hls)
        return h, l, s
    except ImportError:
        pass

    # Pure NumPy implementation of OpenCV BGR2HLS algorithm
    r = img_rgb[:, :, 0].astype(np.float32) / 255.0
    g = img_rgb[:, :, 1].astype(np.float32) / 255.0
    b = img_rgb[:, :, 2].astype(np.float32) / 255.0

    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    diff = max_c - min_c

    l_val = (max_c + min_c) / 2.0

    s_val = np.zeros_like(l_val)
    nonzero_diff = diff > 1e-6
    low_l = nonzero_diff & (l_val <= 0.5)
    high_l = nonzero_diff & (l_val > 0.5)

    s_val[low_l] = diff[low_l] / (max_c[low_l] + min_c[low_l])
    s_val[high_l] = diff[high_l] / (2.0 - max_c[high_l] - min_c[high_l])

    h_val = np.zeros_like(l_val)
    r_max = nonzero_diff & (max_c == r)
    g_max = nonzero_diff & (max_c == g) & (~r_max)
    b_max = nonzero_diff & (~r_max) & (~g_max)

    h_val[r_max] = ((g[r_max] - b[r_max]) / diff[r_max]) % 6.0
    h_val[g_max] = 2.0 + (b[g_max] - r[g_max]) / diff[g_max]
    h_val[b_max] = 4.0 + (r[b_max] - g[b_max]) / diff[b_max]

    h_deg = h_val * 60.0
    h_deg = np.where(h_deg < 0.0, h_deg + 360.0, h_deg)

    # OpenCV divides hue by 2 and rounds to uint8 [0..179]
    h_out = np.clip(np.round(h_deg / 2.0), 0, 180).astype(np.uint8)
    h_out = np.where(h_out >= 180, 0, h_out)
    l_out = np.clip(np.round(l_val * 255.0), 0, 255).astype(np.uint8)
    s_out = np.clip(np.round(s_val * 255.0), 0, 255).astype(np.uint8)

    return h_out, l_out, s_out


def import_legacy_hls(
    image_path: Union[str, Path],
    preset: Literal["holtida-ebl", "learning-shaders"] = "holtida-ebl",
    mode: Literal["corrected", "legacy-exact"] = "corrected",
    pitch_nm: Optional[int] = None,
    apply_radial: bool = True,
) -> Design:
    """Import a legacy image using OpenCV HLS color parameter mapping.

    Args:
      image_path: path to legacy image (PNG, BMP, etc.)
      preset: 'holtida-ebl' (20 µm pitch, ±90° angle, radial -15..+25) or
              'learning-shaders' (60 µm pitch, ±45° angle, radial -5..+20)
      mode: 'corrected' (proper white masking, safe bounds) or
            'legacy-exact' (exact historical behavior for audit)
      pitch_nm: override default pitch if provided
      apply_radial: whether to apply the hue 162 radial gradient override
    """
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"Legacy image not found: {p}")

    with Image.open(p) as im:
        img_rgb = np.array(im.convert("RGB"), dtype=np.uint8)

    h_shape, w_shape, _ = img_rgb.shape

    if preset == "holtida-ebl":
        default_pitch = 20000  # 20 µm
        rot_range = 180.0      # -90 to +90
    else:
        default_pitch = 60000  # 60 µm
        rot_range = 90.0       # -45 to +45

    if pitch_nm is None:
        pitch_nm = default_pitch

    hues_raw, vals_raw, sats_raw = rgb_to_opencv_hls(img_rgb)

    # Hue is scaled to 0-358 even integers
    hues = hues_raw.astype(np.int16) * 2
    sats = sats_raw.astype(np.float64) / 255.0 * 100.0

    # Period table: 360 entries from 0.9 to 1.2 µm
    periods_um = np.linspace(0.9, 1.2, 360)
    periods_disc_um = np.round(periods_um[hues], 2)
    periods_nm = np.round(periods_disc_um * 1000.0).astype(np.uint32)

    # Angles: (sats - 50) / 100 * rot_range
    rots = np.round((sats - 50.0) / 100.0 * rot_range, 0)

    # Activity masking
    if mode == "corrected":
        # Inactive if black (val == 0) or white (val >= 250)
        inactive = (vals_raw == 0) | (vals_raw >= 250)
    else:
        # Legacy exact:
        if preset == "holtida-ebl":
            inactive = (vals_raw == 0) | (vals_raw == 255)
        else:
            # learning-shaders had bug: vals was normalized to 100, then checked == 255 (never true for white)
            inactive = (vals_raw == 0)

    active = ~inactive
    periods_nm[inactive] = 0
    rots[inactive] = 0.0

    # Region masks: extract hue 162 region
    hue_162_mask = (hues == 162) & active
    region_masks = {"hue_162": hue_162_mask}

    # Store normalized appearance RGB for visual fallback
    appearance = img_rgb.astype(np.float32) / 255.0
    fallback = np.mean(appearance, axis=2) / 5.0

    design = Design(
        shape=(h_shape, w_shape),
        pitch_nm=pitch_nm,
        period_nm=periods_nm,
        angle_deg=rots,
        active=active,
        region_masks=region_masks,
        appearance_rgb=appearance,
        fallback_intensity=fallback,
        source_identity=f"legacy-hls:{preset}:{mode}:{p.name}",
    )

    if apply_radial and np.any(hue_162_mask):
        design = apply_radial_gradient(design, mask=hue_162_mask, preset_name=preset)

    return design
