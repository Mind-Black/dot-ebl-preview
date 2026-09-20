"""Canonical Design data model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class OperationRecord:
    """Record of an operation performed on the design."""
    name: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "params": self.params}


@dataclass
class Design:
    """Authoritative physical design for dot-matrix holograms and EBL layouts.

    Coordinates & Units:
      - shape: (height, width) in pixels/cells.
      - pitch_nm: int, holopixel lattice pitch in nanometres (e.g. 20000 nm = 20 µm).
      - period_nm: NDArray[np.uint32], grating period per cell in integer nanometres.
      - angle_deg: NDArray[np.float64], CCW rotation of grating lines from +X
        around +Z. At 0 degrees lines run along X and their reciprocal
        (periodic) direction points along +Y.
      - active: NDArray[np.bool_], boolean activity mask (True = grating present).
      - exposure_mode: str, defaults to 'single_pixel_line' (width = 0 nm).
      - layer: int, GDSII layer (0 to 63, default 1).
      - dose: float, nominal dose factor (default 1.0).
      - region_masks: Dict[str, NDArray[np.bool_]], optional named boolean masks.
      - appearance_rgb: Optional[NDArray[np.float32]], optional appearance RGB image in [0, 1] for visual fallback.
      - fallback_intensity: Optional[NDArray[np.float32]], optional per-cell fallback intensity in [0, 1].
      - source_identity: str, provenance / profile / filename identifier.
      - operations: List[OperationRecord], audit log of applied transforms.
    """

    shape: Tuple[int, int]
    pitch_nm: int
    period_nm: NDArray[np.uint32]
    angle_deg: NDArray[np.float64]
    active: NDArray[np.bool_]
    exposure_mode: str = "single_pixel_line"
    layer: int = 1
    dose: float = 1.0
    region_masks: Dict[str, NDArray[np.bool_]] = field(default_factory=dict)
    appearance_rgb: Optional[NDArray[np.float32]] = None
    fallback_intensity: Optional[NDArray[np.float32]] = None
    source_identity: str = "unknown"
    operations: List[OperationRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate shapes, types, and physical bounds."""
        h, w = self.shape
        if h <= 0 or w <= 0:
            raise ValueError(f"Invalid design dimensions: {self.shape}")
        if self.pitch_nm <= 0:
            raise ValueError(f"pitch_nm must be positive integer, got {self.pitch_nm}")
        if self.period_nm.shape != (h, w):
            raise ValueError(f"period_nm shape {self.period_nm.shape} does not match design shape {self.shape}")
        if self.angle_deg.shape != (h, w):
            raise ValueError(f"angle_deg shape {self.angle_deg.shape} does not match design shape {self.shape}")
        if self.active.shape != (h, w):
            raise ValueError(f"active mask shape {self.active.shape} does not match design shape {self.shape}")

        if not (0 <= self.layer <= 63):
            raise ValueError(f"layer must be between 0 and 63, got {self.layer}")
        if not np.isfinite(self.dose) or self.dose < 0:
            raise ValueError(f"dose factor must be non-negative finite number, got {self.dose}")
        if self.exposure_mode != "single_pixel_line":
            raise ValueError(f"Unsupported exposure_mode: {self.exposure_mode}")

        # Active periods must be positive
        if np.any(self.active & (self.period_nm <= 0)):
            raise ValueError("All active cells must have positive grating periods (period_nm > 0).")

        # Check finite angles
        if np.any(~np.isfinite(self.angle_deg)):
            raise ValueError("angle_deg contains non-finite values (NaN or Inf).")

        for mask_name, mask_arr in self.region_masks.items():
            if mask_arr.shape != (h, w):
                raise ValueError(f"region_mask '{mask_name}' shape {mask_arr.shape} does not match design shape {self.shape}")

        if self.appearance_rgb is not None:
            if self.appearance_rgb.shape != (h, w, 3):
                raise ValueError(f"appearance_rgb shape {self.appearance_rgb.shape} does not match design shape {(h, w, 3)}")

        if self.fallback_intensity is not None:
            if self.fallback_intensity.shape != (h, w):
                raise ValueError(f"fallback_intensity shape {self.fallback_intensity.shape} does not match design shape {self.shape}")

    @property
    def height(self) -> int:
        return self.shape[0]

    @property
    def width(self) -> int:
        return self.shape[1]

    @property
    def active_count(self) -> int:
        return int(np.count_nonzero(self.active))

    def content_hash(self) -> str:
        """Compute stable SHA256 content hash of the physical parameters and metadata."""
        h = hashlib.sha256()
        h.update(f"shape:{self.shape}".encode())
        h.update(f"pitch_nm:{self.pitch_nm}".encode())
        h.update(f"mode:{self.exposure_mode}".encode())
        h.update(f"layer:{self.layer}".encode())
        h.update(f"dose:{self.dose:.6f}".encode())
        h.update(np.ascontiguousarray(self.active).tobytes())
        h.update(np.ascontiguousarray(self.period_nm).tobytes())
        # Quantize angles to 1e-6 degrees for hash stability against micro-float noise
        angle_quant = np.ascontiguousarray(np.round(self.angle_deg, 6))
        h.update(angle_quant.tobytes())
        if self.fallback_intensity is not None:
            h.update(np.ascontiguousarray(np.round(self.fallback_intensity, 4)).tobytes())
        return h.hexdigest()

    def copy(self) -> Design:
        """Create a deep copy of the Design."""
        return Design(
            shape=self.shape,
            pitch_nm=self.pitch_nm,
            period_nm=self.period_nm.copy(),
            angle_deg=self.angle_deg.copy(),
            active=self.active.copy(),
            exposure_mode=self.exposure_mode,
            layer=self.layer,
            dose=self.dose,
            region_masks={k: v.copy() for k, v in self.region_masks.items()},
            appearance_rgb=self.appearance_rgb.copy() if self.appearance_rgb is not None else None,
            fallback_intensity=self.fallback_intensity.copy() if self.fallback_intensity is not None else None,
            source_identity=self.source_identity,
            operations=list(self.operations),
        )
