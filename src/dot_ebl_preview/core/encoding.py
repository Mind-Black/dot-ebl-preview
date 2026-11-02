"""RGB parameter encoding and decoding contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple
import numpy as np
from numpy.typing import NDArray

from dot_ebl_preview.core.model import Design


def round_half_away_from_zero(val: float | NDArray[np.floating]) -> int | NDArray[np.integer]:
    """Round half-away-from-zero (MATLAB/C99 style rounding).

    For x >= 0: floor(x + 0.5)
    For x < 0:  ceil(x - 0.5)
    """
    if isinstance(val, (int, float, np.floating)):
        if val >= 0:
            return int(np.floor(val + 0.5))
        else:
            return int(np.ceil(val - 0.5))
    arr = np.asarray(val, dtype=np.float64)
    res = np.empty_like(arr, dtype=np.int64)
    pos_mask = arr >= 0
    res[pos_mask] = np.floor(arr[pos_mask] + 0.5).astype(np.int64)
    res[~pos_mask] = np.ceil(arr[~pos_mask] - 0.5).astype(np.int64)
    return res


@dataclass
class EncodingReport:
    """Report produced when encoding a Design to an image format."""
    profile_id: str
    policy: str
    active_count: int
    unrepresentable_count: int = 0
    clipped_count: int = 0
    max_period_error_nm: float = 0.0
    rms_period_error_nm: float = 0.0
    max_angle_error_deg: float = 0.0
    rms_angle_error_deg: float = 0.0
    verified: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RGB8IndexedProfile:
    """Profile rgb8-indexed-v1: discrete period and angle lookup tables.

    Encoding Contract:
      - Bit depth: 8-bit unsigned integer (uint8) per channel, RGB image (HxWx3).
      - R channel: Index into `period_lut_nm` (default: 31 entries, 900 + 10*R nm for R=0..30).
      - G channel: Index into `angle_lut_deg` (default: 181 entries, G - 90 deg for G=0..180).
      - B channel: Activity indicator. Must be exactly 255 (active) or 0 (inactive).
        Any other value in the B channel is rejected as an invalid reserved code.
      - Lossless round-trip: Parameter codes and table entries round-trip with zero numerical error.
      - Policies for unrepresentable values:
          * 'reject': Raises ValueError if design contains periods or angles not in the LUTs.
          * 'quantize': Snaps to the nearest LUT entry by physical distance; ties broken by lowest index.
          * allow_clip: If False, raises ValueError for values outside [min(LUT), max(LUT)].
    """
    profile_id: str = "rgb8-indexed-v1"
    period_lut_nm: List[int] = field(default_factory=lambda: [900 + 10 * r for r in range(31)])  # 900..1200 nm
    angle_lut_deg: List[float] = field(default_factory=lambda: [float(g - 90) for g in range(181)])  # -90..90 deg
    active_code: int = 255
    inactive_code: int = 0

    def __post_init__(self) -> None:
        if len(self.period_lut_nm) > 256 or len(self.angle_lut_deg) > 256:
            raise ValueError("LUT entries cannot exceed 256 for 8-bit channels.")
        if len(set(self.period_lut_nm)) != len(self.period_lut_nm):
            raise ValueError("period_lut_nm entries must be unique.")
        if len(set(self.angle_lut_deg)) != len(self.angle_lut_deg):
            raise ValueError("angle_lut_deg entries must be unique.")
        if any(p <= 0 for p in self.period_lut_nm):
            raise ValueError("All period LUT entries must be positive nm.")
        if self.active_code == self.inactive_code:
            raise ValueError("active_code and inactive_code must be distinct.")
        if not (0 <= self.active_code <= 255) or not (0 <= self.inactive_code <= 255):
            raise ValueError("active_code and inactive_code must be in [0, 255].")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "period_lut_nm": self.period_lut_nm,
            "angle_lut_deg": self.angle_lut_deg,
            "active_code": self.active_code,
            "inactive_code": self.inactive_code,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> RGB8IndexedProfile:
        return cls(
            profile_id=d.get("profile_id", "rgb8-indexed-v1"),
            period_lut_nm=d["period_lut_nm"],
            angle_lut_deg=[float(x) for x in d["angle_lut_deg"]],
            active_code=d.get("active_code", 255),
            inactive_code=d.get("inactive_code", 0),
        )

    def decode(self, img_rgb: NDArray[np.uint8], pitch_nm: int = 20000) -> Design:
        """Decode uint8 RGB image to Design."""
        if img_rgb.ndim != 3 or img_rgb.shape[2] != 3:
            raise ValueError(f"Expected HxWx3 uint8 array, got shape {img_rgb.shape}")
        if img_rgb.dtype != np.uint8:
            raise ValueError(f"Expected uint8 dtype, got {img_rgb.dtype}")

        h, w, _ = img_rgb.shape
        r_chan = img_rgb[:, :, 0]
        g_chan = img_rgb[:, :, 1]
        b_chan = img_rgb[:, :, 2]

        # Activity mask check: only active_code (255) and inactive_code (0) are valid
        valid_b = (b_chan == self.active_code) | (b_chan == self.inactive_code)
        if not np.all(valid_b):
            invalid_vals = np.unique(b_chan[~valid_b])
            raise ValueError(f"Reserved B channel values found: {invalid_vals}. B channel must be {self.active_code} or {self.inactive_code}.")

        active = (b_chan == self.active_code)

        # Check LUT boundaries for active pixels
        max_r = len(self.period_lut_nm) - 1
        max_g = len(self.angle_lut_deg) - 1

        active_r = r_chan[active]
        active_g = g_chan[active]

        if np.any(active_r > max_r):
            raise ValueError(f"Active pixel R code {active_r.max()} exceeds period LUT size {len(self.period_lut_nm)}")
        if np.any(active_g > max_g):
            raise ValueError(f"Active pixel G code {active_g.max()} exceeds angle LUT size {len(self.angle_lut_deg)}")

        period_arr = np.array(self.period_lut_nm, dtype=np.uint32)
        angle_arr = np.array(self.angle_lut_deg, dtype=np.float64)

        period_nm = np.zeros((h, w), dtype=np.uint32)
        angle_deg = np.zeros((h, w), dtype=np.float64)

        period_nm[active] = period_arr[active_r]
        angle_deg[active] = angle_arr[active_g]

        return Design(
            shape=(h, w),
            pitch_nm=pitch_nm,
            period_nm=period_nm,
            angle_deg=angle_deg,
            active=active,
            source_identity=f"rgb8-indexed:{self.profile_id}",
        )

    def encode(
        self,
        design: Design,
        policy: Literal["reject", "quantize"] = "reject",
        allow_clip: bool = False,
    ) -> Tuple[NDArray[np.uint8], EncodingReport]:
        """Encode Design to uint8 RGB image under declared policy."""
        h, w = design.shape
        img = np.zeros((h, w, 3), dtype=np.uint8)

        active = design.active
        if not np.any(active):
            report = EncodingReport(profile_id=self.profile_id, policy=policy, active_count=0, verified=True)
            return img, report

        periods = design.period_nm[active]
        angles = design.angle_deg[active]

        period_lut = np.array(self.period_lut_nm, dtype=np.int64)
        angle_lut = np.array(self.angle_lut_deg, dtype=np.float64)

        # Build reverse lookup or match nearest
        r_codes = np.zeros(len(periods), dtype=np.uint8)
        g_codes = np.zeros(len(angles), dtype=np.uint8)

        unrep_count = 0
        clip_count = 0
        period_errors = []
        angle_errors = []

        for i, (p, a) in enumerate(zip(periods, angles)):
            # Period matching
            p_exact = np.where(period_lut == p)[0]
            if len(p_exact) > 0:
                r_codes[i] = p_exact[0]
                period_errors.append(0.0)
            else:
                if policy == "reject":
                    raise ValueError(f"Period {p} nm cannot be represented exactly in profile {self.profile_id} (reject policy).")
                # Quantize: find nearest by absolute difference, tie breaks on lowest index
                diffs = np.abs(period_lut - p)
                nearest_idx = int(np.argmin(diffs))
                if not allow_clip and (p < period_lut.min() or p > period_lut.max()):
                    raise ValueError(f"Period {p} nm is outside LUT range [{period_lut.min()}, {period_lut.max()}] without allow_clip.")
                if p < period_lut.min() or p > period_lut.max():
                    clip_count += 1
                r_codes[i] = nearest_idx
                err = float(abs(period_lut[nearest_idx] - p))
                period_errors.append(err)
                unrep_count += 1

            # Angle matching
            a_exact = np.where(np.isclose(angle_lut, a, atol=1e-9))[0]
            if len(a_exact) > 0:
                g_codes[i] = a_exact[0]
                angle_errors.append(0.0)
            else:
                if policy == "reject":
                    raise ValueError(f"Angle {a}° cannot be represented exactly in profile {self.profile_id} (reject policy).")
                # Directed angle distance (no modulo-180 wrapping)
                diffs = np.abs(angle_lut - a)
                nearest_idx = int(np.argmin(diffs))
                if not allow_clip and (a < angle_lut.min() or a > angle_lut.max()):
                    raise ValueError(f"Angle {a}° is outside LUT range [{angle_lut.min()}, {angle_lut.max()}] without allow_clip.")
                if a < angle_lut.min() or a > angle_lut.max():
                    clip_count += 1
                g_codes[i] = nearest_idx
                err = float(abs(angle_lut[nearest_idx] - a))
                angle_errors.append(err)
                unrep_count += 1

        img[active, 0] = r_codes
        img[active, 1] = g_codes
        img[active, 2] = self.active_code
        img[~active, 2] = self.inactive_code

        # Verification step: decode and compare active regions
        decoded = self.decode(img, pitch_nm=design.pitch_nm)
        assert np.array_equal(decoded.active, design.active), "Activity mask corrupted during RGB8 encode/decode."

        max_p_err = float(max(period_errors)) if period_errors else 0.0
        rms_p_err = float(np.sqrt(np.mean(np.square(period_errors)))) if period_errors else 0.0
        max_a_err = float(max(angle_errors)) if angle_errors else 0.0
        rms_a_err = float(np.sqrt(np.mean(np.square(angle_errors)))) if angle_errors else 0.0

        report = EncodingReport(
            profile_id=self.profile_id,
            policy=policy,
            active_count=int(np.count_nonzero(active)),
            unrepresentable_count=unrep_count,
            clipped_count=clip_count,
            max_period_error_nm=max_p_err,
            rms_period_error_nm=rms_p_err,
            max_angle_error_deg=max_a_err,
            rms_angle_error_deg=rms_a_err,
            verified=True,
        )
        return img, report


@dataclass
class RGB16FixedProfile:
    """Profile rgb16-fixed-v1: 1 nm period grid, 0.01 degree angle grid offset by 32768.

    Encoding Contract:
      - Bit depth: 16-bit unsigned integer (uint16) per channel, RGB image (HxWx3).
      - R channel: Grating period in integer nanometres directly (code = period_nm).
        Enforces min_period_nm (default: 100 nm) <= period <= max_period_nm (default: 100000 nm).
      - G channel: Grating orientation in 0.01° steps offset by 32768:
        code = round_half_away_from_zero(angle_deg * 100.0) + 32768.
        Decoded angle = (code - 32768) / 100.0.
        Covers [-327.68°, +327.67°] with 0.01° physical resolution.
      - B channel: Activity indicator. Must be exactly 65535 (active) or 0 (inactive).
        Any other value in the B channel is rejected as an invalid reserved code.
      - Quantization bounds: Exact on its 1 nm / 0.01° physical lattice. Off-grid values
        introduce <= 0.5 nm and <= 0.005° quantization error before geometry construction.
      - Policies for unrepresentable values:
          * 'reject': Raises ValueError if any angle does not land exactly on the 0.01° grid.
          * 'quantize': Applies half-away-from-zero rounding to the nearest 0.01° grid point.
    """
    profile_id: str = "rgb16-fixed-v1"
    angle_offset: int = 32768
    angle_scale: float = 100.0  # 0.01 deg per step
    active_code: int = 65535
    inactive_code: int = 0
    min_period_nm: int = 100
    max_period_nm: int = 65535

    def __post_init__(self) -> None:
        if self.min_period_nm <= 0:
            raise ValueError(f"min_period_nm must be positive, got {self.min_period_nm}")
        if self.max_period_nm > 65535:
            raise ValueError(f"max_period_nm cannot exceed 65535 for 16-bit channel, got {self.max_period_nm}")
        if self.max_period_nm < self.min_period_nm:
            raise ValueError(f"max_period_nm ({self.max_period_nm}) cannot be less than min_period_nm ({self.min_period_nm})")
        if self.angle_scale <= 0:
            raise ValueError(f"angle_scale must be positive, got {self.angle_scale}")
        if self.active_code == self.inactive_code:
            raise ValueError("active_code and inactive_code must be distinct.")
        if not (0 <= self.active_code <= 65535) or not (0 <= self.inactive_code <= 65535):
            raise ValueError("active_code and inactive_code must be in [0, 65535].")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "angle_offset": self.angle_offset,
            "angle_scale": self.angle_scale,
            "active_code": self.active_code,
            "inactive_code": self.inactive_code,
            "min_period_nm": self.min_period_nm,
            "max_period_nm": self.max_period_nm,
        }

    def decode(self, img_rgb: NDArray[np.uint16], pitch_nm: int = 20000) -> Design:
        """Decode uint16 RGB image to Design."""
        if img_rgb.ndim != 3 or img_rgb.shape[2] != 3:
            raise ValueError(f"Expected HxWx3 uint16 array, got shape {img_rgb.shape}")
        if img_rgb.dtype != np.uint16:
            raise ValueError(f"Expected uint16 dtype, got {img_rgb.dtype}")

        h, w, _ = img_rgb.shape
        r_chan = img_rgb[:, :, 0]
        g_chan = img_rgb[:, :, 1]
        b_chan = img_rgb[:, :, 2]

        valid_b = (b_chan == self.active_code) | (b_chan == self.inactive_code)
        if not np.all(valid_b):
            invalid_vals = np.unique(b_chan[~valid_b])
            raise ValueError(f"Reserved B channel values found: {invalid_vals}. B channel must be {self.active_code} or {self.inactive_code}.")

        active = (b_chan == self.active_code)

        period_nm = np.zeros((h, w), dtype=np.uint32)
        angle_deg = np.zeros((h, w), dtype=np.float64)

        if np.any(active):
            act_r = r_chan[active].astype(np.uint32)
            if np.any(act_r < self.min_period_nm) or np.any(act_r > self.max_period_nm):
                raise ValueError(f"Active periods outside configured limits [{self.min_period_nm}, {self.max_period_nm}] nm.")

            period_nm[active] = act_r
            # Signed angles: (G - 32768) / 100.0
            act_g = g_chan[active].astype(np.float64)
            angle_deg[active] = (act_g - self.angle_offset) / self.angle_scale

        return Design(
            shape=(h, w),
            pitch_nm=pitch_nm,
            period_nm=period_nm,
            angle_deg=angle_deg,
            active=active,
            source_identity=f"rgb16-fixed:{self.profile_id}",
        )

    def encode(
        self,
        design: Design,
        policy: Literal["reject", "quantize"] = "reject",
    ) -> Tuple[NDArray[np.uint16], EncodingReport]:
        """Encode Design to uint16 RGB image."""
        h, w = design.shape
        img = np.zeros((h, w, 3), dtype=np.uint16)

        active = design.active
        if not np.any(active):
            report = EncodingReport(profile_id=self.profile_id, policy=policy, active_count=0, verified=True)
            return img, report

        periods = design.period_nm[active]
        angles = design.angle_deg[active]

        # Check period bounds
        if np.any(periods < self.min_period_nm) or np.any(periods > self.max_period_nm):
            raise ValueError(f"Periods outside bounds [{self.min_period_nm}, {self.max_period_nm}] nm.")

        r_codes = periods.astype(np.uint16)

        # Angles: round(angle_deg * 100) + 32768 with signed half-away-from-zero rounding
        scaled_angles = angles * self.angle_scale
        rounded_angles = round_half_away_from_zero(scaled_angles)
        g_codes_raw = rounded_angles + self.angle_offset

        if np.any(g_codes_raw < 0) or np.any(g_codes_raw > 65535):
            raise ValueError("Angle value exceeds 16-bit code range [-327.68°, +327.67°].")

        # Check exact representability under reject
        recovered_angles = (g_codes_raw.astype(np.float64) - self.angle_offset) / self.angle_scale
        angle_diffs = np.abs(recovered_angles - angles)

        unrep = int(np.count_nonzero(angle_diffs > 1e-7))
        if policy == "reject" and unrep > 0:
            max_err = float(np.max(angle_diffs))
            raise ValueError(f"Angles cannot be represented exactly on 0.01° grid (max deviation {max_err:.5f}°). Use policy='quantize'.")

        g_codes = g_codes_raw.astype(np.uint16)

        img[active, 0] = r_codes
        img[active, 1] = g_codes
        img[active, 2] = self.active_code
        img[~active, 2] = self.inactive_code

        # Verification step
        decoded = self.decode(img, pitch_nm=design.pitch_nm)
        assert np.array_equal(decoded.active, design.active), "Activity mask mismatch in 16-bit decode."
        assert np.array_equal(decoded.period_nm[active], design.period_nm[active]), "Period array mismatch in 16-bit decode."

        max_a_err = float(np.max(angle_diffs)) if len(angle_diffs) > 0 else 0.0
        rms_a_err = float(np.sqrt(np.mean(np.square(angle_diffs)))) if len(angle_diffs) > 0 else 0.0

        report = EncodingReport(
            profile_id=self.profile_id,
            policy=policy,
            active_count=int(np.count_nonzero(active)),
            unrepresentable_count=unrep,
            max_period_error_nm=0.0,
            rms_period_error_nm=0.0,
            max_angle_error_deg=max_a_err,
            rms_angle_error_deg=rms_a_err,
            verified=True,
        )
        return img, report


@dataclass
class RGBAContinuousProfile:
    """Profile rgba-continuous-v1: Continuous linear mapping for Truecolor + Alpha (RGBA) images.

    Encoding Contract:
      - Supports both 8-bit (uint8) and 16-bit (uint16) Truecolor + Alpha PNGs (PNG color type 6).
      - R Channel (Period): Continuous linear mapping across [min_period_nm, max_period_nm] nm.
        Default range is 400.0 to 1600.0 nm.
        Formula: period = min_period_nm + (R / R_max) * (max_period_nm - min_period_nm).
      - G Channel (Angle): Continuous linear mapping across [min_angle_deg, max_angle_deg] degrees.
        Default range is -90.0 to +90.0 deg.
        Formula: angle = min_angle_deg + (G / G_max) * (max_angle_deg - min_angle_deg).
      - B Channel (Reserved / Unused): Ignored on decode; set to 0 when exporting.
      - A Channel (Activation Flag): Thresholded at 50% opacity (A >= 128 for 8-bit, A >= 32768 for 16-bit).
        Inactive cells output period = 0, angle = 0.
      - Noise & Anti-Aliasing Mitigation (Masked Bilateral Filter):
        Valid-only bilateral filter on ingest (enabled by default):
        * Period filtering: Valid-only scalar bilateral filter.
        * Angle filtering: Valid-only axial bilateral filter with nearest-branch lifting.
    """
    profile_id: str = "rgba-continuous-v1"
    min_period_nm: float = 400.0
    max_period_nm: float = 1600.0
    min_angle_deg: float = -90.0
    max_angle_deg: float = 90.0
    apply_filter: bool = True
    round_integer_angles: bool = False
    round_period_50nm: bool = False
    filter_diameter: int = 3
    filter_sigma_color_period: float = 50.0
    filter_sigma_color_angle: float = 10.0
    filter_sigma_space: float = 100.0

    def __post_init__(self) -> None:
        if self.min_period_nm <= 0:
            raise ValueError(f"min_period_nm must be positive, got {self.min_period_nm}")
        if self.max_period_nm <= self.min_period_nm:
            raise ValueError(f"max_period_nm ({self.max_period_nm}) must be greater than min_period_nm ({self.min_period_nm})")
        if self.max_angle_deg <= self.min_angle_deg:
            raise ValueError(f"max_angle_deg ({self.max_angle_deg}) must be greater than min_angle_deg ({self.min_angle_deg})")
        if self.filter_diameter < 1:
            raise ValueError(f"filter_diameter must be >= 1, got {self.filter_diameter}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "min_period_nm": self.min_period_nm,
            "max_period_nm": self.max_period_nm,
            "min_angle_deg": self.min_angle_deg,
            "max_angle_deg": self.max_angle_deg,
            "apply_filter": self.apply_filter,
            "round_integer_angles": self.round_integer_angles,
            "round_period_50nm": self.round_period_50nm,
            "filter_diameter": self.filter_diameter,
            "filter_sigma_color_period": self.filter_sigma_color_period,
            "filter_sigma_color_angle": self.filter_sigma_color_angle,
            "filter_sigma_space": self.filter_sigma_space,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> RGBAContinuousProfile:
        return cls(
            profile_id=d.get("profile_id", "rgba-continuous-v1"),
            min_period_nm=float(d.get("min_period_nm", 400.0)),
            max_period_nm=float(d.get("max_period_nm", 1600.0)),
            min_angle_deg=float(d.get("min_angle_deg", -90.0)),
            max_angle_deg=float(d.get("max_angle_deg", 90.0)),
            apply_filter=bool(d.get("apply_filter", True)),
            round_integer_angles=bool(d.get("round_integer_angles", False)),
            round_period_50nm=bool(d.get("round_period_50nm", False)),
            filter_diameter=int(d.get("filter_diameter", 3)),
            filter_sigma_color_period=float(d.get("filter_sigma_color_period", 50.0)),
            filter_sigma_color_angle=float(d.get("filter_sigma_color_angle", 10.0)),
            filter_sigma_space=float(d.get("filter_sigma_space", 100.0)),
        )

    def decode(self, img_rgba: NDArray[np.uint8 | np.uint16], pitch_nm: int = 20000) -> Design:
        """Decode uint8 or uint16 RGBA image to Design."""
        if img_rgba.ndim != 3 or img_rgba.shape[2] != 4:
            raise ValueError(f"Expected HxWx4 RGBA array, got shape {img_rgba.shape}")
        if img_rgba.dtype not in (np.uint8, np.uint16):
            raise ValueError(f"Expected uint8 or uint16 dtype, got {img_rgba.dtype}")

        h, w, _ = img_rgba.shape
        r_chan = img_rgba[:, :, 0]
        g_chan = img_rgba[:, :, 1]
        # b_chan = img_rgba[:, :, 2] is ignored
        a_chan = img_rgba[:, :, 3]

        max_val = 65535.0 if img_rgba.dtype == np.uint16 else 255.0
        alpha_thresh = 32768 if img_rgba.dtype == np.uint16 else 128

        active = a_chan >= alpha_thresh

        period_nm = np.zeros((h, w), dtype=np.uint32)
        angle_deg = np.zeros((h, w), dtype=np.float64)

        if np.any(active):
            r_norm = r_chan[active].astype(np.float64) / max_val
            raw_period = self.min_period_nm + r_norm * (self.max_period_nm - self.min_period_nm)
            period_nm[active] = round_half_away_from_zero(raw_period).astype(np.uint32)

            g_norm = g_chan[active].astype(np.float64) / max_val
            raw_angle = self.min_angle_deg + g_norm * (self.max_angle_deg - self.min_angle_deg)
            angle_deg[active] = raw_angle

        design = Design(
            shape=(h, w),
            pitch_nm=pitch_nm,
            period_nm=period_nm,
            angle_deg=angle_deg,
            active=active,
            source_identity=f"rgba-continuous:{self.profile_id}",
        )

        if self.apply_filter and np.any(active):
            from dot_ebl_preview.core.filters import apply_masked_bilateral_filter
            design = apply_masked_bilateral_filter(
                design,
                diameter=self.filter_diameter,
                sigma_color_period=self.filter_sigma_color_period,
                sigma_color_angle=self.filter_sigma_color_angle,
                sigma_space=self.filter_sigma_space,
                filter_period=True,
                filter_angle=True,
            )

        if self.round_period_50nm and np.any(design.active):
            design.period_nm[design.active] = (
                round_half_away_from_zero(design.period_nm[design.active] / 50.0) * 50
            ).astype(np.uint32)

        if self.round_integer_angles and np.any(design.active):
            design.angle_deg[design.active] = round_half_away_from_zero(
                design.angle_deg[design.active]
            ).astype(np.float64)

        return design

    def encode(
        self,
        design: Design,
        bit_depth: Literal[8, 16] = 8,
    ) -> Tuple[NDArray[np.uint8 | np.uint16], EncodingReport]:
        """Encode Design to uint8 or uint16 RGBA image."""
        h, w = design.shape
        dtype = np.uint16 if bit_depth == 16 else np.uint8
        max_val = 65535.0 if bit_depth == 16 else 255.0
        img = np.zeros((h, w, 4), dtype=dtype)

        active = design.active
        if not np.any(active):
            report = EncodingReport(profile_id=self.profile_id, policy="continuous", active_count=0, verified=True)
            return img, report

        periods = design.period_nm[active].astype(np.float64)
        angles = design.angle_deg[active].astype(np.float64)

        period_span = self.max_period_nm - self.min_period_nm
        angle_span = self.max_angle_deg - self.min_angle_deg

        norm_p = np.clip((periods - self.min_period_nm) / period_span, 0.0, 1.0)
        norm_a = np.clip((angles - self.min_angle_deg) / angle_span, 0.0, 1.0)

        r_codes = round_half_away_from_zero(norm_p * max_val).astype(dtype)
        g_codes = round_half_away_from_zero(norm_a * max_val).astype(dtype)

        img[active, 0] = r_codes
        img[active, 1] = g_codes
        img[active, 2] = 0
        img[active, 3] = int(max_val)

        # Verification step (without filter to measure encoding loss)
        from dataclasses import replace
        unfiltered_prof = replace(self, apply_filter=False)
        decoded = unfiltered_prof.decode(img, pitch_nm=design.pitch_nm)
        assert np.array_equal(decoded.active, design.active), "Activity mask mismatch in RGBA decode."

        period_errs = np.abs(decoded.period_nm[active].astype(np.float64) - periods)
        angle_errs = np.abs(decoded.angle_deg[active] - angles)

        max_p_err = float(np.max(period_errs)) if len(period_errs) > 0 else 0.0
        rms_p_err = float(np.sqrt(np.mean(np.square(period_errs)))) if len(period_errs) > 0 else 0.0
        max_a_err = float(np.max(angle_errs)) if len(angle_errs) > 0 else 0.0
        rms_a_err = float(np.sqrt(np.mean(np.square(angle_errs)))) if len(angle_errs) > 0 else 0.0

        report = EncodingReport(
            profile_id=self.profile_id,
            policy="continuous",
            active_count=int(np.count_nonzero(active)),
            max_period_error_nm=max_p_err,
            rms_period_error_nm=rms_p_err,
            max_angle_error_deg=max_a_err,
            rms_angle_error_deg=rms_a_err,
            verified=True,
        )
        return img, report
