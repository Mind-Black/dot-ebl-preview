"""Command line interface for dot-ebl-preview.

Available Subcommands:
  - inspect: Inspect a canonical design (.npz) or RGB encoded image, reporting physical
    parameters, grid extents, unique periods/angles, and SHA256 hashes.
  - import-legacy: Import historical OpenCV HLS or Unity HSV images into an authoritative
    Design (.npz) file, supporting preset migration modes, radial overrides, and filters.
  - export: Generate and atomically publish a complete Raith EBL fabrication bundle
    (.gds with single-pixel paths, angles.txt, gratings.txt, design.npz, manifest.json).
  - preview: Render an optical diffraction preview to a PNG image using the CPU spectral engine.

Examples:
  $ dot-ebl inspect design.npz
  $ dot-ebl import-legacy test.bmp --preset holtida-ebl --mode corrected -o design.npz
  $ dot-ebl export design.npz --name HOLO_CHIP -o ./_OUTPUT
  $ dot-ebl preview design.npz -o preview.png --preset corrected
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from dot_ebl_preview.api import (
    build_design,
    build_layout,
    export_bundle,
    inspect_design,
)
from dot_ebl_preview.core.encoding import RGB8IndexedProfile, RGB16FixedProfile
from dot_ebl_preview.core.filters import apply_bilateral_filter, apply_gaussian_filter
from dot_ebl_preview.core.resample import downscale_design
from dot_ebl_preview.io.artifacts import load_design_artifact, save_design_artifact
from dot_ebl_preview.io.legacy_hls import import_legacy_hls
from dot_ebl_preview.io.legacy_unity import import_legacy_unity_hsv
from dot_ebl_preview.preview.renderer import render_preview_to_file


def main(args: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dot-ebl",
        description="Combined hologram optical preview and Raith EBL layout application",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect a design (.npz) or image file")
    p_inspect.add_argument("input", help="Path to .npz or RGB/RGBA image file")
    p_inspect.add_argument("--profile", default="rgb8-indexed-v1", choices=["rgb8-indexed-v1", "rgb16-fixed-v1", "rgba-continuous-v1"])
    p_inspect.add_argument("--pitch-um", type=float, default=20.0, help="Pixel pitch in µm")
    p_inspect.add_argument("--min-period-nm", type=float, default=400.0, help="Min period in nm (RGBA continuous)")
    p_inspect.add_argument("--max-period-nm", type=float, default=1600.0, help="Max period in nm (RGBA continuous)")
    p_inspect.add_argument("--min-angle-deg", type=float, default=-90.0, help="Min angle in deg (RGBA continuous)")
    p_inspect.add_argument("--max-angle-deg", type=float, default=90.0, help="Max angle in deg (RGBA continuous)")
    p_inspect.add_argument("--filter", action=argparse.BooleanOptionalAction, default=True, help="Smooth gradients via masked bilateral filter (RGBA continuous)")
    p_inspect.add_argument("--round-angles", action=argparse.BooleanOptionalAction, default=False, help="Round active angles to integer degrees (RGBA continuous)")
    p_inspect.add_argument("--round-period-50nm", action=argparse.BooleanOptionalAction, default=False, help="Round active grating periods to 50 nm increments (RGBA continuous)")

    # import-legacy
    p_import = subparsers.add_parser("import-legacy", help="Import legacy image and save as design.npz")
    p_import.add_argument("input", help="Path to legacy image file")
    p_import.add_argument("--preset", default="holtida-ebl", choices=["holtida-ebl", "learning-shaders", "unity-hsv"])
    p_import.add_argument("--mode", default="corrected", choices=["corrected", "legacy-exact"])
    p_import.add_argument("--pitch-um", type=float, default=None, help="Pixel pitch in µm (default: preset-specific)")
    p_import.add_argument("--downscale", type=int, default=1)
    p_import.add_argument("--filter", choices=["none", "gaussian", "bilateral"], default="none")
    p_import.add_argument("--output", "-o", required=True, help="Output .npz path")

    # export
    p_export = subparsers.add_parser("export", help="Export EBL fabrication bundle")
    p_export.add_argument("input", help="Path to design (.npz) or parameter image")
    p_export.add_argument("--name", default="HOLOGRAM", help="Layout name")
    p_export.add_argument("--output-dir", "-o", default="_OUTPUT", help="Output directory")
    p_export.add_argument("--profile", default="rgb8-indexed-v1", choices=["rgb8-indexed-v1", "rgb16-fixed-v1", "rgba-continuous-v1"])
    p_export.add_argument("--pitch-um", type=float, default=20.0)
    p_export.add_argument("--min-period-nm", type=float, default=400.0, help="Min period in nm (RGBA continuous)")
    p_export.add_argument("--max-period-nm", type=float, default=1600.0, help="Max period in nm (RGBA continuous)")
    p_export.add_argument("--min-angle-deg", type=float, default=-90.0, help="Min angle in deg (RGBA continuous)")
    p_export.add_argument("--max-angle-deg", type=float, default=90.0, help="Max angle in deg (RGBA continuous)")
    p_export.add_argument("--filter", action=argparse.BooleanOptionalAction, default=True, help="Smooth gradients via masked bilateral filter (RGBA continuous)")
    p_export.add_argument("--round-angles", action=argparse.BooleanOptionalAction, default=False, help="Round active angles to integer degrees (RGBA continuous)")
    p_export.add_argument("--round-period-50nm", action=argparse.BooleanOptionalAction, default=False, help="Round active grating periods to 50 nm increments (RGBA continuous)")
    p_export.add_argument(
        "--angles",
        nargs="*",
        type=float,
        default=[0.0, 45.0, 90.0, 135.0],
        help="Azimuth angles in degrees for preview images (default: 0 45 90 135)",
    )
    p_export.add_argument(
        "--no-angles",
        action="store_true",
        help="Disable rendering preview images in the exported bundle",
    )


    # preview
    p_preview = subparsers.add_parser("preview", help="Render optical preview image")
    p_preview.add_argument("input", help="Path to design (.npz) or parameter image")
    p_preview.add_argument("--output", "-o", required=True, help="Output PNG image path")
    p_preview.add_argument("--preset", default="corrected", choices=["corrected", "glsl-legacy", "unity-hsv"])
    p_preview.add_argument("--profile", default="rgb8-indexed-v1", choices=["rgb8-indexed-v1", "rgb16-fixed-v1", "rgba-continuous-v1"])
    p_preview.add_argument("--pitch-um", type=float, default=20.0)
    p_preview.add_argument("--min-period-nm", type=float, default=400.0, help="Min period in nm (RGBA continuous)")
    p_preview.add_argument("--max-period-nm", type=float, default=1600.0, help="Max period in nm (RGBA continuous)")
    p_preview.add_argument("--min-angle-deg", type=float, default=-90.0, help="Min angle in deg (RGBA continuous)")
    p_preview.add_argument("--max-angle-deg", type=float, default=90.0, help="Max angle in deg (RGBA continuous)")
    p_preview.add_argument("--filter", action=argparse.BooleanOptionalAction, default=True, help="Smooth gradients via masked bilateral filter (RGBA continuous)")
    p_preview.add_argument("--round-angles", action=argparse.BooleanOptionalAction, default=False, help="Round active angles to integer degrees (RGBA continuous)")
    p_preview.add_argument("--round-period-50nm", action=argparse.BooleanOptionalAction, default=False, help="Round active grating periods to 50 nm increments (RGBA continuous)")
    p_preview.add_argument("--aperture-mm", type=float, default=2.0, help="Observer aperture radius in mm (default: 2.0)")
    p_preview.add_argument("--light-size-mm", type=float, default=20.0, help="Light source physical radius in mm (default: 20.0)")
    p_preview.add_argument(
        "--light",
        action="append",
        nargs="+",
        type=float,
        metavar="VAL",
        help="Specify light source: X Y Z [size_mm] [intensity] (can be specified multiple times for multiple lights)",
    )


    parsed = parser.parse_args(args)

    if parsed.command == "inspect":
        in_path = Path(parsed.input)
        if in_path.suffix.lower() == ".npz":
            design = load_design_artifact(in_path)
        else:
            pitch_nm = int(round(parsed.pitch_um * 1000.0))
            design = build_design(
                in_path,
                encoding_profile=parsed.profile,
                pitch_nm=pitch_nm,
                min_period_nm=getattr(parsed, "min_period_nm", 400.0),
                max_period_nm=getattr(parsed, "max_period_nm", 1600.0),
                min_angle_deg=getattr(parsed, "min_angle_deg", -90.0),
                max_angle_deg=getattr(parsed, "max_angle_deg", 90.0),
                apply_filter=getattr(parsed, "filter", True),
                round_integer_angles=getattr(parsed, "round_angles", False),
                round_period_50nm=getattr(parsed, "round_period_50nm", False),
            )
        info = inspect_design(design)
        print(json.dumps(info, indent=2))
        return 0

    elif parsed.command == "import-legacy":
        in_path = Path(parsed.input)
        pitch_nm = int(round(parsed.pitch_um * 1000.0)) if parsed.pitch_um is not None else None
        if parsed.preset == "unity-hsv":
            design = import_legacy_unity_hsv(in_path, pitch_nm=pitch_nm)
        else:
            design = import_legacy_hls(in_path, preset=parsed.preset, mode=parsed.mode, pitch_nm=pitch_nm)

        if parsed.downscale > 1:
            design = downscale_design(design, parsed.downscale)

        if parsed.filter == "gaussian":
            design = apply_gaussian_filter(design, sigma=1.0)
        elif parsed.filter == "bilateral":
            design = apply_bilateral_filter(design, diameter=3, sigma_color=10.0, sigma_space=100.0)

        out_path = Path(parsed.output)
        save_design_artifact(out_path, design)
        print(f"Imported legacy design saved to {out_path}")
        return 0

    elif parsed.command == "export":
        in_path = Path(parsed.input)
        pitch_nm = int(round(parsed.pitch_um * 1000.0))
        if in_path.suffix.lower() == ".npz":
            design = load_design_artifact(in_path)
        else:
            design = build_design(
                in_path,
                encoding_profile=parsed.profile,
                pitch_nm=pitch_nm,
                min_period_nm=getattr(parsed, "min_period_nm", 400.0),
                max_period_nm=getattr(parsed, "max_period_nm", 1600.0),
                min_angle_deg=getattr(parsed, "min_angle_deg", -90.0),
                max_angle_deg=getattr(parsed, "max_angle_deg", 90.0),
                apply_filter=getattr(parsed, "filter", True),
                round_integer_angles=getattr(parsed, "round_angles", False),
                round_period_50nm=getattr(parsed, "round_period_50nm", False),
            )

        render_angles = None if parsed.no_angles else parsed.angles
        out_dir = export_bundle(
            design,
            output_dir=parsed.output_dir,
            layout_name=parsed.name,
            render_angles=render_angles,
        )
        print(f"Exported bundle to {out_dir}")
        return 0


    elif parsed.command == "preview":
        in_path = Path(parsed.input)
        pitch_nm = int(round(parsed.pitch_um * 1000.0))
        if in_path.suffix.lower() == ".npz":
            design = load_design_artifact(in_path)
        else:
            design = build_design(
                in_path,
                encoding_profile=parsed.profile,
                pitch_nm=pitch_nm,
                min_period_nm=getattr(parsed, "min_period_nm", 400.0),
                max_period_nm=getattr(parsed, "max_period_nm", 1600.0),
                min_angle_deg=getattr(parsed, "min_angle_deg", -90.0),
                max_angle_deg=getattr(parsed, "max_angle_deg", 90.0),
                apply_filter=getattr(parsed, "filter", True),
                round_integer_angles=getattr(parsed, "round_angles", False),
                round_period_50nm=getattr(parsed, "round_period_50nm", False),
            )

        from dataclasses import replace
        from dot_ebl_preview.optics.engine import LightSource
        from dot_ebl_preview.optics.presets import get_optical_preset

        preset_params = get_optical_preset(parsed.preset)
        if parsed.light:
            lights = []
            for l_vals in parsed.light:
                if len(l_vals) < 3:
                    raise ValueError(f"--light requires at least 3 values (X Y Z), got {l_vals}")
                pos = (float(l_vals[0]), float(l_vals[1]), float(l_vals[2]))
                s_mm = float(l_vals[3]) if len(l_vals) > 3 else parsed.light_size_mm
                intens = float(l_vals[4]) if len(l_vals) > 4 else 1.0
                lights.append(LightSource(pos=pos, source_radius_factor=s_mm, intensity=intens))
            params = replace(
                preset_params,
                aperture_radius_factor=parsed.aperture_mm,
                lights=tuple(lights),
            )
        else:
            params = replace(
                preset_params,
                aperture_radius_factor=parsed.aperture_mm,
                source_radius_factor=parsed.light_size_mm,
            )
        out_file = render_preview_to_file(design, parsed.output, preset=parsed.preset, params=params)

        print(f"Optical preview saved to {out_file}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
