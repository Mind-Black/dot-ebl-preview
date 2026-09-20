"""Legacy Unity HSV importer (HologramShader.shader compatibility)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from dot_ebl_preview.core.model import Design


# Calibrated laser periods and hues from learning-shaders load_tables.py / HologramShader.shader
UNITY_PERIOD_REAL_NM = [1328, 1263, 1225, 1175, 1128, 1066, 1016, 903]
UNITY_LASER_HUES = [
    6.0 / 360.0,
    25.0 / 360.0,
    39.0 / 360.0,
    58.0 / 360.0,
    90.0 / 360.0,
    125.0 / 360.0,
    159.0 / 360.0,
    205.0 / 360.0,
]


def shader_rgb_to_hsv(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Exact port of the Unity shader's rgb2hsv function (HologramShader.shader:424-435)."""
    # K = float4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0)
    # p = lerp(float4(c.bg, K.wz), float4(c.gb, K.xy), step(c.b, c.g))
    if c_b_step := (b <= g):
        p_x, p_y, p_z, p_w = g, b, 0.0, -1.0 / 3.0
    else:
        p_x, p_y, p_z, p_w = b, g, -1.0, 2.0 / 3.0

    # q = lerp(float4(p.xyw, c.r), float4(c.r, p.yzx), step(p.x, c.r))
    if p_x <= r:
        q_x, q_y, q_z, q_w = r, p_y, p_z, p_x
    else:
        q_x, q_y, q_z, q_w = p_x, p_y, p_w, r

    d = q_x - min(q_w, q_y)
    e = 1.0e-10
    h = abs(q_z + (q_w - q_y) / (6.0 * d + e))
    s = d / (q_x + e)
    v = q_x
    return float(h), float(s), float(v)


def get_unity_grating_nm(h: float, s: float) -> int:
    """Exact port of Unity shader getGrating (lines 437-459)."""
    if s < 0.1:
        return 0
    if h > 0.7:
        return UNITY_PERIOD_REAL_NM[0]

    closest = 10000000.0
    clos_idx = 0
    for i in range(8):
        diff = abs(h - UNITY_LASER_HUES[i])
        # Strict < inequality ensures first entry wins equal-distance ties
        if diff < closest:
            closest = diff
            clos_idx = i
    return UNITY_PERIOD_REAL_NM[clos_idx]


def import_legacy_unity_hsv(
    image_path: Union[str, Path],
    min_angle_deg: float = -10.0,
    max_angle_deg: float = 10.0,
    pitch_nm: Optional[int] = 60000,
) -> Design:
    """Import a legacy appearance image using the Unity shader HSV algorithm.

    Preserves source appearance and fallback grayscale field.
    """
    if pitch_nm is None:
        pitch_nm = 60000

    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"Unity source image not found: {p}")

    with Image.open(p) as im:
        img_rgb_uint8 = np.array(im.convert("RGB"), dtype=np.uint8)

    h_shape, w_shape, _ = img_rgb_uint8.shape
    appearance = img_rgb_uint8.astype(np.float32) / 255.0

    # Derive fallback grayscale: source channel mean divided by 5 (matching lines 597-603)
    fallback_intensity = np.mean(appearance, axis=2) / 5.0

    period_nm = np.zeros((h_shape, w_shape), dtype=np.uint32)
    angle_deg = np.zeros((h_shape, w_shape), dtype=np.float64)
    active = np.zeros((h_shape, w_shape), dtype=np.bool_)

    for r in range(h_shape):
        for c in range(w_shape):
            r_val, g_val, b_val = appearance[r, c, 0], appearance[r, c, 1], appearance[r, c, 2]
            h, s, _ = shader_rgb_to_hsv(r_val, g_val, b_val)
            grating_nm = get_unity_grating_nm(h, s)
            if grating_nm > 0:
                active[r, c] = True
                period_nm[r, c] = grating_nm
                # rotation = pictureColorHSV.y * (_MaxAngle - _MinAngle) + _MinAngle
                rot = s * (max_angle_deg - min_angle_deg) + min_angle_deg
                angle_deg[r, c] = rot

    return Design(
        shape=(h_shape, w_shape),
        pitch_nm=pitch_nm,
        period_nm=period_nm,
        angle_deg=angle_deg,
        active=active,
        appearance_rgb=appearance,
        fallback_intensity=fallback_intensity,
        source_identity=f"legacy-unity-hsv:{p.name}",
    )
