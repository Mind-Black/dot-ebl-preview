"""Public typed Python API for dot-ebl-preview."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np

from dot_ebl_preview.core.encoding import (
    RGB8IndexedProfile,
    RGB16FixedProfile,
    RGBAContinuousProfile,
)
from dot_ebl_preview.core.filters import (
    apply_bilateral_filter,
    apply_gaussian_filter,
    apply_masked_bilateral_filter,
)
from dot_ebl_preview.core.model import Design
from dot_ebl_preview.core.operations import apply_radial_gradient
from dot_ebl_preview.core.resample import downscale_design
from dot_ebl_preview.io.artifacts import load_design_artifact, save_design_artifact
from dot_ebl_preview.io.images import load_image_rgb, load_image_raw, save_image_rgba
from dot_ebl_preview.io.legacy_hls import import_legacy_hls
from dot_ebl_preview.io.legacy_unity import import_legacy_unity_hsv
from dot_ebl_preview.jobs.bundle import stage_and_export_bundle
from dot_ebl_preview.layout.plan import FabricationPlan, create_fabrication_plan
from dot_ebl_preview.optics.engine import (
    LightSource,
    OpticalSimParams,
    simulate_cell_optical_color,
    render_optical_preview,
)
from dot_ebl_preview.preview.renderer import render_preview_to_file



def build_design(
    image_path: Union[str, Path],
    encoding_profile: str = "rgb8-indexed-v1",
    pitch_nm: int = 20000,
    downscale_factor: int = 1,
    min_period_nm: float = 400.0,
    max_period_nm: float = 1600.0,
    min_angle_deg: float = -90.0,
    max_angle_deg: float = 90.0,
    apply_filter: bool = True,
    round_integer_angles: bool = False,
    round_period_50nm: bool = False,
) -> Design:
    """Build an authoritative, validated physical Design from an RGB or RGBA encoded parameter image.

    Args:
        image_path: Path to the encoded PNG/BMP image containing grating parameters.
        encoding_profile: Profile name for channel decoding. Supported values:
            - 'rgb8-indexed-v1' / 'RGB8 indexed': uint8 RGB image with discrete LUTs (R=period index,
              G=angle index, B=activity flag: 0=inactive, 255=active).
            - 'rgb16-fixed-v1' / 'RGB16 fixed': uint16 RGB image with fixed physical grid (R=period in nm,
              G=angle in 0.01 deg with 32768 offset, B=activity flag: 0=inactive, 65535=active).
            - 'rgba-continuous-v1' / 'RGBA continuous': uint8 or uint16 Truecolor+Alpha PNG image (R=linear period,
              G=linear angle, B=unused, A>=50% opacity flag).
        pitch_nm: Holopixel lattice spacing in nanometres (default: 20000 nm = 20 µm).
        downscale_factor: Integer downsampling factor using nearest-neighbor indexing (default: 1).
        min_period_nm: Minimum grating period in nm for RGBA continuous profile (default: 400.0 nm).
        max_period_nm: Maximum grating period in nm for RGBA continuous profile (default: 1600.0 nm).
        min_angle_deg: Minimum grating orientation in degrees for RGBA continuous profile (default: -90.0 deg).
        max_angle_deg: Maximum grating orientation in degrees for RGBA continuous profile (default: +90.0 deg).
        apply_filter: Whether to apply masked bilateral filter on ingest for RGBA continuous (default: True).
        round_integer_angles: Whether to round active angles to integer degrees for RGBA continuous (default: False).
        round_period_50nm: Whether to round active grating periods to 50 nm increments for RGBA continuous (default: False).

    Returns:
        Design: Authoritative physical design containing grid dimensions, integer period array,
            float64 CCW rotation angles, boolean activity mask, and provenance metadata.

    Raises:
        FileNotFoundError: If image_path does not exist.
        ValueError: If image channel depth does not match profile or contains invalid reserved codes.

    Example:
        >>> from dot_ebl_preview.api import build_design
        >>> design = build_design("hologram_params.png", encoding_profile="rgba-continuous-v1", pitch_nm=20000)
        >>> print(design.shape, design.active_count)
    """
    img = load_image_raw(image_path)
    if encoding_profile in ("rgb8-indexed-v1", "RGB8 indexed"):
        profile8 = RGB8IndexedProfile()
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]
        if img.dtype != np.uint8:
            raise ValueError(f"rgb8-indexed-v1 requires uint8 image, got {img.dtype}")
        design = profile8.decode(img, pitch_nm=pitch_nm)
    elif encoding_profile in ("rgb16-fixed-v1", "RGB16 fixed"):
        profile16 = RGB16FixedProfile()
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]
        if img.dtype != np.uint16:
            raise ValueError(f"rgb16-fixed-v1 requires uint16 image, got {img.dtype}")
        design = profile16.decode(img, pitch_nm=pitch_nm)
    elif encoding_profile in ("rgba-continuous-v1", "RGBA continuous"):
        profile_rgba = RGBAContinuousProfile(
            min_period_nm=min_period_nm,
            max_period_nm=max_period_nm,
            min_angle_deg=min_angle_deg,
            max_angle_deg=max_angle_deg,
            apply_filter=apply_filter,
            round_integer_angles=round_integer_angles,
            round_period_50nm=round_period_50nm,
        )
        design = profile_rgba.decode(img, pitch_nm=pitch_nm)
    else:
        raise ValueError(f"Unknown encoding profile: {encoding_profile}")

    if downscale_factor > 1:
        design = downscale_design(design, downscale_factor)

    return design


def build_layout(design: Design, top_name: str = "HOLOGRAM") -> FabricationPlan:
    """Derive an immutable FabricationPlan and Raith GDSII hierarchy from an authoritative Design.

    Builds deduplicated circular-envelope holopixel cell definitions (with width=0 single-pixel
    exposure lines) and hierarchical SREF placements for all active grid cells.

    Args:
        design: Authoritative Design instance.
        top_name: Name for the top-level GDSII structure (sanitized to <=32 ASCII chars).

    Returns:
        FabricationPlan: Frozen layout plan containing the RaithLibrary, cell name mapping,
            extents, stripe counts, and SHA256 plan hash.

    Example:
        >>> from dot_ebl_preview.api import build_layout
        >>> plan = build_layout(design, top_name="HOLOGRAM_CHIP")
        >>> print(plan.total_stripes, plan.unique_periods_count)
    """
    return create_fabrication_plan(design, top_name=top_name)


def export_bundle(
    design: Design,
    output_dir: Union[str, Path],
    layout_name: str = "HOLOGRAM",
    render_angles: Optional[Sequence[float]] = (0.0, 45.0, 90.0, 135.0),
    preview_preset: str = "corrected",
) -> Path:
    """Stage and publish a complete, atomic EBL fabrication export bundle.

    The bundle is staged in a hidden temporary directory on the destination volume
    and atomically renamed upon successful verification of all file checksums.

    Generated Artifacts:
        - `{layout_name}.gds`: Raith GDSII stream with zero-width single-pixel paths and SREFs.
        - `angles.txt`: 2D float text array of grating angles in degrees (-1000.0 sentinel for inactive).
        - `gratings.txt`: 2D float text array of grating periods in µm (0.0 sentinel for inactive).
        - `design.npz`: Complete canonical design arrays and metadata (pickle-free NumPy archive).
        - `manifest.json`: Verification manifest with SHA-256 hashes, stripe counts, and timestamps.
        - Optical preview PNGs at specified azimuth angles (e.g. `preview_angle_az0.png`, `preview.png`).

    Args:
        design: Authoritative Design instance to export.
        output_dir: Destination parent directory where the timestamped bundle folder will be created.
        layout_name: Base name for layout structures and files (default: 'HOLOGRAM').
        render_angles: Optional sequence of azimuth angles to render previews for (default: 0, 45, 90, 135 deg).
        preview_preset: Optical preset to use for preview rendering ('corrected', 'glsl-legacy', 'unity-hsv').

    Returns:
        Path: Absolute path to the finalized, published bundle directory.

    Raises:
        RuntimeError: If bundle staging or file serialization fails (cleans up staging directory).

    Example:
        >>> from dot_ebl_preview.api import export_bundle
        >>> bundle_dir = export_bundle(design, output_dir="./_OUTPUT", layout_name="SAMPLE")
        >>> print(f"Published bundle to: {bundle_dir}")
    """
    return stage_and_export_bundle(
        design,
        output_parent_dir=output_dir,
        layout_name=layout_name,
        render_angles=render_angles,
        preview_preset=preview_preset,
    )



def inspect_design(design: Design) -> Dict[str, Any]:
    """Inspect design statistics, physical parameters, extents, and content hashes.

    Args:
        design: Authoritative Design instance to inspect.

    Returns:
        Dict[str, Any]: Dictionary containing:
            - 'shape': (height, width) tuple in cells.
            - 'pitch_nm' / 'pitch_um': Holopixel lattice spacing.
            - 'active_cells' / 'total_cells' / 'active_percentage': Activity metrics.
            - 'unique_periods_nm' / 'unique_periods_um': List of distinct grating periods present.
            - 'unique_angles_deg': List of distinct orientation angles present.
            - 'total_stripes' / 'skipped_stripes': Exposure geometry counts.
            - 'extents_um': Physical bounding box dict ('x_min', 'x_max', 'y_min', 'y_max').
            - 'content_hash': SHA-256 hash uniquely identifying design parameter arrays.
    """
    plan = create_fabrication_plan(design)
    active = design.active
    uniq_periods = np.unique(design.period_nm[active]) if np.any(active) else np.array([])
    uniq_angles = np.unique(design.angle_deg[active]) if np.any(active) else np.array([])

    return {
        "shape": design.shape,
        "pitch_nm": design.pitch_nm,
        "pitch_um": design.pitch_nm / 1000.0,
        "active_cells": design.active_count,
        "total_cells": design.width * design.height,
        "active_percentage": (design.active_count / (design.width * design.height)) * 100.0,
        "unique_periods_nm": uniq_periods.tolist(),
        "unique_periods_um": (uniq_periods / 1000.0).tolist(),
        "unique_angles_deg": uniq_angles.tolist(),
        "total_stripes": plan.total_stripes,
        "skipped_stripes": plan.skipped_degenerate_stripes,
        "extents_um": {
            "x_min": plan.extents.x_min_nm / 1000.0,
            "x_max": plan.extents.x_max_nm / 1000.0,
            "y_min": plan.extents.y_min_nm / 1000.0,
            "y_max": plan.extents.y_max_nm / 1000.0,
        },
        "content_hash": design.content_hash(),
    }


def dot_matrix_hologram(
    name: Optional[str] = None,
    image: str = "test.bmp",
    px_size: float = 20.0,
    write: bool = False,
    downscale_factor: int = 1,
    rotation_filter: bool = False,
    output_dir: Union[str, Path] = "_OUTPUT",
    render_angles: Optional[Sequence[float]] = (0.0, 45.0, 90.0, 135.0),
) -> Optional[FabricationPlan]:
    """Compatibility wrapper matching historical Holtida-EBL dot_matrix_hologram signature.

    Provides backwards compatibility for legacy scripts. Translates input image via
    legacy OpenCV HLS mapping ('holtida-ebl' preset with corrected masks), applies
    optional bilateral filtering, and conditionally exports the bundle.

    Args:
        name: Name for the layout. If None, derives from image stem.
        image: Path or filename of the legacy parameter image (checks cwd and _INPUT/).
        px_size: Holopixel pitch in micrometres (default: 20.0 µm).
        write: If True, exports bundle to disk and returns FabricationPlan. If False,
            returns None without disk writes (matching legacy preview-only behavior).
        downscale_factor: Integer downsampling factor (default: 1).
        rotation_filter: If True, applies bilateral angle smoothing (d=3, sigmaColor=10, sigmaSpace=100).
        output_dir: Output parent directory for bundle publication (default: '_OUTPUT').
        render_angles: Optional sequence of azimuth angles to render previews for when write=True.

    Returns:
        Optional[FabricationPlan]: FabricationPlan if write=True, otherwise None.

    Raises:
        FileNotFoundError: If image file cannot be found in cwd or _INPUT/.
    """
    layout_name = name if name is not None else Path(image).stem
    pitch_nm = int(round(px_size * 1000.0))

    # Resolve image path
    img_path = Path(image)
    if not img_path.exists():
        cwd_input = Path.cwd() / "_INPUT" / image
        if cwd_input.exists():
            img_path = cwd_input
        else:
            raise FileNotFoundError(f"Image not found: {image}")

    # Legacy import with Holtida-EBL preset
    design = import_legacy_hls(
        img_path,
        preset="holtida-ebl",
        mode="corrected",
        pitch_nm=pitch_nm,
        apply_radial=True,
    )

    if downscale_factor > 1:
        design = downscale_design(design, downscale_factor)

    if rotation_filter:
        design = apply_bilateral_filter(design, diameter=3, sigma_color=10.0, sigma_space=100.0)

    if write:
        export_bundle(
            design,
            output_dir=output_dir,
            layout_name=layout_name,
            render_angles=render_angles,
        )
        return build_layout(design, top_name=layout_name)

    return None
