"""Project artifact persistence: design.npz (allow_pickle=False) and metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union
import numpy as np

from dot_ebl_preview.core.model import Design, OperationRecord


def save_design_artifact(path: Union[str, Path], design: Design) -> None:
    """Save Design to a self-contained .npz file (with allow_pickle=False guaranteed on read)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    metadata: Dict[str, Any] = {
        "shape": list(design.shape),
        "pitch_nm": design.pitch_nm,
        "exposure_mode": design.exposure_mode,
        "layer": design.layer,
        "dose": design.dose,
        "source_identity": design.source_identity,
        "region_mask_keys": list(design.region_masks.keys()),
        "has_appearance": design.appearance_rgb is not None,
        "has_fallback": design.fallback_intensity is not None,
        "operations": [op.to_dict() for op in design.operations],
    }

    arrays: Dict[str, Any] = {
        "metadata_json": np.array([json.dumps(metadata)], dtype=np.str_),
        "period_nm": design.period_nm,
        "angle_deg": design.angle_deg,
        "active": design.active,
    }

    for k, v in design.region_masks.items():
        arrays[f"mask_{k}"] = v

    if design.appearance_rgb is not None:
        arrays["appearance_rgb"] = design.appearance_rgb

    if design.fallback_intensity is not None:
        arrays["fallback_intensity"] = design.fallback_intensity

    np.savez_compressed(p, **arrays)


def load_design_artifact(path: Union[str, Path]) -> Design:
    """Load Design from a .npz file strictly enforcing allow_pickle=False."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Design artifact not found: {p}")

    with np.load(p, allow_pickle=False) as data:
        meta_str = str(data["metadata_json"][0])
        metadata = json.loads(meta_str)

        shape = tuple(metadata["shape"])
        pitch_nm = int(metadata["pitch_nm"])
        exposure_mode = str(metadata.get("exposure_mode", "single_pixel_line"))
        layer = int(metadata.get("layer", 1))
        dose = float(metadata.get("dose", 1.0))
        source_identity = str(metadata.get("source_identity", "unknown"))

        period_nm = data["period_nm"].astype(np.uint32)
        angle_deg = data["angle_deg"].astype(np.float64)
        active = data["active"].astype(np.bool_)

        region_masks = {}
        for k in metadata.get("region_mask_keys", []):
            mask_key = f"mask_{k}"
            if mask_key in data:
                region_masks[k] = data[mask_key].astype(np.bool_)

        appearance_rgb = None
        if metadata.get("has_appearance") and "appearance_rgb" in data:
            appearance_rgb = data["appearance_rgb"].astype(np.float32)

        fallback_intensity = None
        if metadata.get("has_fallback") and "fallback_intensity" in data:
            fallback_intensity = data["fallback_intensity"].astype(np.float32)

        operations = [
            OperationRecord(name=op["name"], params=op.get("params", {}))
            for op in metadata.get("operations", [])
        ]

    return Design(
        shape=shape,  # type: ignore
        pitch_nm=pitch_nm,
        period_nm=period_nm,
        angle_deg=angle_deg,
        active=active,
        exposure_mode=exposure_mode,
        layer=layer,
        dose=dose,
        region_masks=region_masks,
        appearance_rgb=appearance_rgb,
        fallback_intensity=fallback_intensity,
        source_identity=source_identity,
        operations=operations,
    )
