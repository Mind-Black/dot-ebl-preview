"""Edge case and numerical stability tests for dot-ebl-preview.

Covers:
  - Zero-active layouts and empty designs
  - Single-pixel designs (1x1 active and inactive)
  - Boundary coordinates, large coordinate grids, GDSII 32-bit limits, odd pitch snapping
  - Holopixel boundary geometry, chord degeneracy, extreme periods
  - Format errors, corruption, and strict contract validation
  - Numerical stability under extreme angles and spectral diffraction bounds
"""

from __future__ import annotations

import io
import json
import math
import struct
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image
import pytest

from dot_ebl_preview.api import (
    build_design,
    build_layout,
    export_bundle,
    inspect_design,
)
from dot_ebl_preview.core.encoding import (
    RGB8IndexedProfile,
    RGB16FixedProfile,
    round_half_away_from_zero,
)
from dot_ebl_preview.core.filters import apply_bilateral_filter, apply_gaussian_filter
from dot_ebl_preview.core.grid import (
    Extents,
    cell_center_nm,
    centered_preview_offset_nm,
    design_extents_nm,
    grid_centers_nm,
)
from dot_ebl_preview.core.model import Design, OperationRecord
from dot_ebl_preview.core.operations import apply_radial_gradient
from dot_ebl_preview.core.resample import downscale_design
from dot_ebl_preview.io.artifacts import load_design_artifact, save_design_artifact
from dot_ebl_preview.io.images import load_image_rgb
from dot_ebl_preview.io.text_exports import export_text_parameters
from dot_ebl_preview.jobs.bundle import stage_and_export_bundle
from dot_ebl_preview.layout.holopixel import generate_holopixel_stripes
from dot_ebl_preview.layout.placements import build_hologram_layout
from dot_ebl_preview.layout.plan import create_fabrication_plan
from dot_ebl_preview.optics.engine import (
    OpticalSimParams,
    render_optical_preview,
    simulate_cell_optical_color,
)
from dot_ebl_preview.preview.renderer import render_preview_to_file
from dot_ebl_preview.raith.records import (
    excess64_decode,
    excess64_encode,
    pack_gds_record,
)
from dot_ebl_preview.raith.writer import write_gds_stream


# =========================================================================
# SECTION 1: Zero-Active / Empty Layout Edge Cases
# =========================================================================

class TestZeroActiveLayouts:
    """Rigorous tests for zero-active / empty designs across all pipeline stages."""

    @pytest.fixture
    def empty_design(self) -> Design:
        shape = (4, 4)
        return Design(
            shape=shape,
            pitch_nm=20000,
            period_nm=np.zeros(shape, dtype=np.uint32),
            angle_deg=np.zeros(shape, dtype=np.float64),
            active=np.zeros(shape, dtype=np.bool_),
            source_identity="empty_test_fixture",
        )

    def test_empty_design_model_properties(self, empty_design: Design):
        assert empty_design.active_count == 0
        assert empty_design.width == 4
        assert empty_design.height == 4
        h = empty_design.content_hash()
        assert isinstance(h, str) and len(h) == 64
        # Deep copy must match
        copied = empty_design.copy()
        assert copied.content_hash() == h

    def test_empty_design_inspect(self, empty_design: Design):
        info = inspect_design(empty_design)
        assert info["active_cells"] == 0
        assert info["total_cells"] == 16
        assert info["active_percentage"] == 0.0
        assert info["unique_periods_nm"] == []
        assert info["unique_angles_deg"] == []
        assert info["total_stripes"] == 0
        assert info["skipped_stripes"] == 0

    def test_empty_design_layout_and_hierarchy(self, empty_design: Design):
        plan = create_fabrication_plan(empty_design, top_name="EMPTY_HOLO")
        assert plan.active_cells == 0
        assert plan.total_stripes == 0
        assert plan.skipped_degenerate_stripes == 0
        assert plan.unique_periods_count == 0
        assert len(plan.holopixel_structures) == 0

        # Library should have exactly 1 structure: the top structure with 0 elements
        assert "EMPTY_HOLO" in plan.library.structures
        top_s = plan.library.structures["EMPTY_HOLO"]
        assert len(top_s.elements) == 0
        plan.library.validate_hierarchy()

    def test_empty_design_gdsii_binary_serialization(self, empty_design: Design):
        plan = create_fabrication_plan(empty_design, top_name="EMPTY_GDS")
        buf = io.BytesIO()
        write_gds_stream(plan.library, buf)
        raw_bytes = buf.getvalue()

        # Parse GDSII stream records independently
        offset = 0
        records = []
        while offset < len(raw_bytes):
            rec_len, rectype, datatype = struct.unpack_from(">HBB", raw_bytes, offset)
            records.append((rectype, datatype))
            offset += rec_len

        rectypes = [r[0] for r in records]
        # Must have: HEADER(0), BGNLIB(1), LIBNAME(2), UNITS(3), BGNSTR(5), STRNAME(6), ENDSTR(7), ENDLIB(4)
        assert rectypes[0] == 0
        assert rectypes[1] == 1
        assert rectypes[2] == 2
        assert rectypes[3] == 3
        assert rectypes[-1] == 4
        # Must NOT contain PATH (9) or SREF (10) since there are no active elements
        assert 9 not in rectypes
        assert 10 not in rectypes

    def test_empty_design_text_parameter_exports(self, empty_design: Design, tmp_path: Path):
        angles_p, gratings_p = export_text_parameters(tmp_path, empty_design)
        assert angles_p.exists()
        assert gratings_p.exists()

        angles = np.loadtxt(angles_p)
        gratings = np.loadtxt(gratings_p)
        assert angles.shape == (4, 4)
        assert gratings.shape == (4, 4)
        # Inactive sentinel checks
        assert np.all(angles == -1000.0)
        assert np.all(gratings == 0.0)

    def test_empty_design_bundle_export(self, empty_design: Design, tmp_path: Path):
        out_dir = stage_and_export_bundle(empty_design, output_parent_dir=tmp_path, layout_name="EMPTY_BUNDLE")
        assert out_dir.exists()
        assert (out_dir / "EMPTY_BUNDLE.gds").exists()
        assert (out_dir / "angles.txt").exists()
        assert (out_dir / "gratings.txt").exists()
        assert (out_dir / "design.npz").exists()
        assert (out_dir / "manifest.json").exists()

        with open(out_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["status"] == "COMPLETED"
        assert manifest["active_cells"] == 0
        assert manifest["total_stripes"] == 0

    def test_empty_design_preview_rendering(self, empty_design: Design, tmp_path: Path):
        # Empty without fallback should render black
        preview_float = render_optical_preview(empty_design)
        assert preview_float.shape == (4, 4, 3)
        assert np.all(preview_float == 0.0)
        assert not np.any(np.isnan(preview_float))

        # Empty with fallback intensity
        empty_with_fb = empty_design.copy()
        empty_with_fb.fallback_intensity = np.full((4, 4), 0.5, dtype=np.float32)
        preview_fb = render_optical_preview(empty_with_fb)
        assert np.allclose(preview_fb, 0.5)

        # File rendering
        out_png = tmp_path / "empty_preview.png"
        render_preview_to_file(empty_design, out_png)
        assert out_png.exists()

    def test_empty_design_encoding_roundtrips(self, empty_design: Design):
        # RGB8
        p8 = RGB8IndexedProfile()
        img8, rep8 = p8.encode(empty_design, policy="reject")
        assert rep8.active_count == 0
        assert np.all(img8[:, :, 2] == 0)  # B channel 0
        dec8 = p8.decode(img8, pitch_nm=empty_design.pitch_nm)
        assert dec8.active_count == 0

        # RGB16
        p16 = RGB16FixedProfile()
        img16, rep16 = p16.encode(empty_design, policy="reject")
        assert rep16.active_count == 0
        assert np.all(img16[:, :, 2] == 0)
        dec16 = p16.decode(img16, pitch_nm=empty_design.pitch_nm)
        assert dec16.active_count == 0

    def test_empty_design_transforms(self, empty_design: Design):
        # Downscale
        down = downscale_design(empty_design, factor=2)
        assert down.shape == (2, 2)
        assert down.active_count == 0

        # Gaussian & Bilateral filters on empty layout
        g_filtered = apply_gaussian_filter(empty_design, sigma=1.0)
        assert g_filtered.active_count == 0

        b_filtered = apply_bilateral_filter(empty_design)
        assert b_filtered.active_count == 0

        # Radial gradient on empty layout
        rad = apply_radial_gradient(empty_design)
        assert rad.active_count == 0


# =========================================================================
# SECTION 2: Single-Pixel Designs (1x1)
# =========================================================================

class TestSinglePixelDesigns:
    """Rigorous tests for minimal 1x1 designs."""

    @pytest.fixture
    def single_pixel_active(self) -> Design:
        return Design(
            shape=(1, 1),
            pitch_nm=20000,
            period_nm=np.array([[1000]], dtype=np.uint32),
            angle_deg=np.array([[45.0]], dtype=np.float64),
            active=np.array([[True]], dtype=np.bool_),
            source_identity="single_px_active",
        )

    @pytest.fixture
    def single_pixel_inactive(self) -> Design:
        return Design(
            shape=(1, 1),
            pitch_nm=20000,
            period_nm=np.array([[0]], dtype=np.uint32),
            angle_deg=np.array([[0.0]], dtype=np.float64),
            active=np.array([[False]], dtype=np.bool_),
            source_identity="single_px_inactive",
        )

    def test_single_pixel_active_extents_and_center(self, single_pixel_active: Design):
        ext = design_extents_nm(1, 1, 20000)
        assert ext.x_min_nm == 0
        assert ext.x_max_nm == 20000
        assert ext.y_min_nm == -20000
        assert ext.y_max_nm == 0
        assert ext.width_nm == 20000
        assert ext.height_nm == 20000

        cx, cy = cell_center_nm(0, 0, 20000)
        assert cx == 10000
        assert cy == -10000

        off_x, off_y = centered_preview_offset_nm(1, 1, 20000)
        assert off_x == -10000.0
        assert off_y == 10000.0

    def test_single_pixel_active_fabrication_plan(self, single_pixel_active: Design):
        plan = create_fabrication_plan(single_pixel_active, top_name="SINGLE_PX_HOLO")
        assert plan.total_cells == 1
        assert plan.active_cells == 1
        assert plan.unique_periods_count == 1
        assert 1000 in plan.holopixel_structures
        struct_name = plan.holopixel_structures[1000]
        assert struct_name == "P_1000"

        # Check structures in library
        assert "P_1000" in plan.library.structures
        cell_struct = plan.library.structures["P_1000"]
        assert len(cell_struct.elements) > 0

        # Check top structure placement
        top_struct = plan.library.structures["SINGLE_PX_HOLO"]
        assert len(top_struct.elements) == 1
        sref = top_struct.elements[0]
        assert sref.name == "P_1000"
        assert sref.origin_nm == (10000, -10000)
        assert sref.angle_deg == 45.0

    def test_single_pixel_active_gdsii_record_validation(self, single_pixel_active: Design):
        plan = create_fabrication_plan(single_pixel_active, top_name="TOP_SINGLE")
        buf = io.BytesIO()
        write_gds_stream(plan.library, buf)
        data = buf.getvalue()

        # Parse GDSII records and verify exact placement
        offset = 0
        sref_found = False
        sref_angle = None
        sref_origin = None

        while offset < len(data):
            rec_len, rectype, datatype = struct.unpack_from(">HBB", data, offset)
            payload = data[offset + 4 : offset + rec_len]
            if rectype == 10:  # SREF
                sref_found = True
            elif sref_found and rectype == 28:  # ANGLE
                sref_angle = excess64_decode(payload)
            elif sref_found and rectype == 16:  # XY
                sref_origin = struct.unpack(">ii", payload)
                break
            offset += rec_len

        assert sref_found
        assert abs(sref_angle - 45.0) < 1e-6
        assert sref_origin == (10000, -10000)

    def test_single_pixel_active_text_exports(self, single_pixel_active: Design, tmp_path: Path):
        ang_p, grat_p = export_text_parameters(tmp_path, single_pixel_active)
        angles = np.loadtxt(ang_p)
        gratings = np.loadtxt(grat_p)
        assert angles.ndim == 0
        assert float(angles) == 45.0
        assert float(gratings) == 1.0  # 1000 nm = 1.0 µm

    def test_single_pixel_downscale_constraints(self, single_pixel_active: Design):
        # Downscale with factor 1 returns copy
        d1 = downscale_design(single_pixel_active, factor=1)
        assert d1.shape == (1, 1)

        # Downscale with factor 2 on 1x1 raises ValueError
        with pytest.raises(ValueError, match="too large for design of shape"):
            downscale_design(single_pixel_active, factor=2)

    def test_single_pixel_inactive_plan(self, single_pixel_inactive: Design):
        plan = create_fabrication_plan(single_pixel_inactive, top_name="INACTIVE_1X1")
        assert plan.active_cells == 0
        assert plan.total_cells == 1
        assert plan.total_stripes == 0
        assert len(plan.library.structures["INACTIVE_1X1"].elements) == 0


# =========================================================================
# SECTION 3: Boundary Coordinates, Large Grids & Snapping
# =========================================================================

class TestBoundaryCoordinatesAndGrids:
    """Tests for physical coordinate calculation, snapping, boundary grids, and limits."""

    def test_asymmetric_grid_extents(self):
        # 1 row x 500 columns
        ext_wide = design_extents_nm(height=1, width=500, pitch_nm=20000)
        assert ext_wide.width_nm == 10_000_000
        assert ext_wide.height_nm == 20000
        assert ext_wide.x_max_nm == 10_000_000
        assert ext_wide.y_min_nm == -20000

        # 500 rows x 1 column
        ext_tall = design_extents_nm(height=500, width=1, pitch_nm=20000)
        assert ext_tall.width_nm == 20000
        assert ext_tall.height_nm == 10_000_000
        assert ext_tall.y_min_nm == -10_000_000

    def test_odd_pitch_half_grid_snapping_symmetry(self):
        # Pitch = 1 nm
        # (0, 0): x_exact = 0.5, y_exact = -0.5
        # Round half away from zero: 0.5 -> 1, -0.5 -> -1
        x, y = cell_center_nm(0, 0, pitch_nm=1, snap=True)
        assert x == 1
        assert y == -1

        # Pitch = 3 nm
        # (0, 0): x_exact = 1.5 -> 2, y_exact = -1.5 -> -2
        x3, y3 = cell_center_nm(0, 0, pitch_nm=3, snap=True)
        assert x3 == 2
        assert y3 == -2

        # Rounding function direct validation
        assert round_half_away_from_zero(0.5) == 1
        assert round_half_away_from_zero(-0.5) == -1
        assert round_half_away_from_zero(2.5) == 3
        assert round_half_away_from_zero(-2.5) == -3
        assert round_half_away_from_zero(100.5) == 101
        assert round_half_away_from_zero(-100.5) == -101

    def test_large_grid_centers_performance(self):
        # 1000 x 1000 grid (1,000,000 cells)
        x_grid, y_grid = grid_centers_nm(1000, 1000, 20000)
        assert x_grid.shape == (1000, 1000)
        assert y_grid.shape == (1000, 1000)

        # Top-left cell (0, 0)
        assert x_grid[0, 0] == 10000
        assert y_grid[0, 0] == -10000

        # Bottom-right cell (999, 999)
        # x = (999 + 0.5) * 20000 = 19,990,000 nm
        # y = -(999 + 0.5) * 20000 = -19,990,000 nm
        assert x_grid[999, 999] == 19990000
        assert y_grid[999, 999] == -19990000

    def test_gdsii_int32_boundary_coordinates(self):
        # GDSII format uses signed 32-bit integers for coordinates
        # Max positive int32: 2,147,483,647 nm (~2.147 meters)
        # Min negative int32: -2,147,483,648 nm (~-2.147 meters)
        max_int32 = 2_147_483_647
        min_int32 = -2_147_483_648

        # Pack and unpack XY record at limits
        packed_max = pack_gds_record(16, 3, [max_int32, min_int32])
        # Unpack: length (2 bytes), rectype (1 byte), datatype (1 byte), payload
        payload = packed_max[4:]
        unpacked_x, unpacked_y = struct.unpack(">ii", payload)
        assert unpacked_x == max_int32
        assert unpacked_y == min_int32


# =========================================================================
# SECTION 4: Holopixel Stripe Geometry & Degenerate Chords
# =========================================================================

class TestHolopixelGeometryEdgeCases:
    """Tests for stripe circle clipping, chord boundaries, and degenerate cases."""

    def test_period_equals_pitch(self):
        # Period = 20000, Pitch = 20000
        # Stripe at y = -10000 + 10000 = 0 (central chord across circle diameter)
        paths, skipped = generate_holopixel_stripes(pitch_nm=20000, period_nm=20000)
        assert len(paths) == 1
        p = paths[0]
        assert p.width_nm == 0
        (x1, y1), (x2, y2) = p.vertices_nm
        assert y1 == 0 and y2 == 0
        assert x1 == -10000
        assert x2 == 10000

    def test_period_greater_than_pitch(self):
        # Period = 25000, Pitch = 20000
        paths, skipped = generate_holopixel_stripes(pitch_nm=20000, period_nm=25000)
        assert len(paths) <= 1
        for p in paths:
            assert p.width_nm == 0

    def test_very_fine_grating_period(self):
        # Fine period = 200 nm on 20 µm pitch (~100 stripes)
        paths, skipped = generate_holopixel_stripes(pitch_nm=20000, period_nm=200)
        assert len(paths) > 90
        # All endpoints must be distinct integers
        for p in paths:
            (x1, y1), (x2, y2) = p.vertices_nm
            assert isinstance(x1, int) and isinstance(y1, int)
            assert isinstance(x2, int) and isinstance(y2, int)
            assert x1 < x2

    def test_invalid_pitch_or_period_rejected(self):
        with pytest.raises(ValueError, match="must be positive"):
            generate_holopixel_stripes(pitch_nm=0, period_nm=1000)

        with pytest.raises(ValueError, match="must be positive"):
            generate_holopixel_stripes(pitch_nm=20000, period_nm=-500)


# =========================================================================
# SECTION 5: Format Errors & Strict Validation Contracts
# =========================================================================

class TestValidationAndFormatErrors:
    """Tests for design bounds validation and format error rejection."""

    def test_design_invalid_dimensions(self):
        with pytest.raises(ValueError, match="Invalid design dimensions"):
            Design(
                shape=(0, 5),
                pitch_nm=20000,
                period_nm=np.zeros((0, 5), dtype=np.uint32),
                angle_deg=np.zeros((0, 5), dtype=np.float64),
                active=np.zeros((0, 5), dtype=np.bool_),
            )

    def test_design_invalid_pitch(self):
        with pytest.raises(ValueError, match="pitch_nm must be positive"):
            Design(
                shape=(2, 2),
                pitch_nm=0,
                period_nm=np.full((2, 2), 1000, dtype=np.uint32),
                angle_deg=np.zeros((2, 2), dtype=np.float64),
                active=np.ones((2, 2), dtype=np.bool_),
            )

    def test_design_active_cell_zero_period_prohibited(self):
        # Active cells MUST have period > 0
        with pytest.raises(ValueError, match="All active cells must have positive grating periods"):
            Design(
                shape=(2, 2),
                pitch_nm=20000,
                period_nm=np.array([[1000, 0], [1000, 1000]], dtype=np.uint32),
                angle_deg=np.zeros((2, 2), dtype=np.float64),
                active=np.array([[True, True], [True, True]], dtype=np.bool_),
            )

    def test_design_non_finite_angles_prohibited(self):
        # NaN in angle_deg
        with pytest.raises(ValueError, match="contains non-finite values"):
            Design(
                shape=(2, 2),
                pitch_nm=20000,
                period_nm=np.full((2, 2), 1000, dtype=np.uint32),
                angle_deg=np.array([[0.0, np.nan], [0.0, 0.0]], dtype=np.float64),
                active=np.ones((2, 2), dtype=np.bool_),
            )

        # Inf in angle_deg
        with pytest.raises(ValueError, match="contains non-finite values"):
            Design(
                shape=(2, 2),
                pitch_nm=20000,
                period_nm=np.full((2, 2), 1000, dtype=np.uint32),
                angle_deg=np.array([[0.0, np.inf], [0.0, 0.0]], dtype=np.float64),
                active=np.ones((2, 2), dtype=np.bool_),
            )

    def test_design_layer_bounds(self):
        with pytest.raises(ValueError, match="layer must be between 0 and 63"):
            Design(
                shape=(2, 2),
                pitch_nm=20000,
                period_nm=np.full((2, 2), 1000, dtype=np.uint32),
                angle_deg=np.zeros((2, 2), dtype=np.float64),
                active=np.ones((2, 2), dtype=np.bool_),
                layer=64,
            )

    def test_design_dose_bounds(self):
        with pytest.raises(ValueError, match="dose factor must be non-negative"):
            Design(
                shape=(2, 2),
                pitch_nm=20000,
                period_nm=np.full((2, 2), 1000, dtype=np.uint32),
                angle_deg=np.zeros((2, 2), dtype=np.float64),
                active=np.ones((2, 2), dtype=np.bool_),
                dose=-0.5,
            )

    def test_design_shape_mismatch(self):
        with pytest.raises(ValueError, match="period_nm shape"):
            Design(
                shape=(2, 2),
                pitch_nm=20000,
                period_nm=np.full((3, 2), 1000, dtype=np.uint32),
                angle_deg=np.zeros((2, 2), dtype=np.float64),
                active=np.ones((2, 2), dtype=np.bool_),
            )

    def test_load_image_corrupt_or_jpeg(self, tmp_path: Path):
        # Non-existent
        with pytest.raises(FileNotFoundError):
            load_image_rgb(tmp_path / "does_not_exist.png")

        # Prohibited JPEG
        jpg = tmp_path / "image.jpeg"
        jpg.write_bytes(b"dummy")
        with pytest.raises(ValueError, match="JPEG format is prohibited"):
            load_image_rgb(jpg)

    def test_load_artifact_corrupt(self, tmp_path: Path):
        # Non-existent .npz
        with pytest.raises(FileNotFoundError):
            load_design_artifact(tmp_path / "not_found.npz")

        # Corrupted .npz file (not valid zip)
        corrupt = tmp_path / "corrupt.npz"
        corrupt.write_bytes(b"not a valid zip file content")
        with pytest.raises(Exception):
            load_design_artifact(corrupt)

    def test_rgb8_profile_validation_errors(self):
        p8 = RGB8IndexedProfile()

        # Reserved B channel error
        bad_img = np.zeros((2, 2, 3), dtype=np.uint8)
        bad_img[0, 0, 2] = 127  # Neither 0 nor 255
        with pytest.raises(ValueError, match="Reserved B channel values"):
            p8.decode(bad_img)

        # Incompatible shape
        with pytest.raises(ValueError, match="Expected HxWx3"):
            p8.decode(np.zeros((2, 2), dtype=np.uint8))  # type: ignore

    def test_rgb16_profile_validation_errors(self):
        p16 = RGB16FixedProfile()

        # Reserved B channel error
        bad_img = np.zeros((2, 2, 3), dtype=np.uint16)
        bad_img[0, 0, 2] = 32768  # Neither 0 nor 65535
        with pytest.raises(ValueError, match="Reserved B channel values"):
            p16.decode(bad_img)

        # Active period outside limit
        bad_img2 = np.zeros((1, 1, 3), dtype=np.uint16)
        bad_img2[0, 0, 0] = 50  # Below min_period_nm (100 nm)
        bad_img2[0, 0, 2] = 65535  # Active
        with pytest.raises(ValueError, match="Active periods outside"):
            p16.decode(bad_img2)


# =========================================================================
# SECTION 6: Numerical Stability & Precision
# =========================================================================

class TestNumericalStability:
    """Tests for numerical stability under boundary angles, diffraction parameters, and float precision."""

    def test_extreme_angles_in_layout_sref(self):
        # Angles beyond 360 or negative
        angles = [-720.0, -360.0, -180.0, -90.0, 0.0, 90.0, 180.0, 360.0, 720.0]
        shape = (1, len(angles))
        period_nm = np.full(shape, 1000, dtype=np.uint32)
        angle_deg = np.array([angles], dtype=np.float64)
        active = np.ones(shape, dtype=np.bool_)

        design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
        plan = create_fabrication_plan(design, top_name="EXTREME_ANGLES")

        top_struct = plan.library.structures["EXTREME_ANGLES"]
        assert len(top_struct.elements) == len(angles)

        buf = io.BytesIO()
        write_gds_stream(plan.library, buf)
        raw = buf.getvalue()
        assert len(raw) > 0

    def test_optical_simulation_extreme_periods(self):
        # Period far below visible (UV / deep sub-wavelength)
        r, g, b = simulate_cell_optical_color(period_nm=100, angle_deg=0.0)
        assert 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0
        assert not any(math.isnan(v) for v in (r, g, b))

        # Period far above visible (100,000 nm = 100 µm, no visible diffraction order)
        r, g, b = simulate_cell_optical_color(period_nm=100000, angle_deg=0.0)
        assert 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0
        assert not any(math.isnan(v) for v in (r, g, b))

    def test_excess64_float_serialization_precision(self):
        values = [
            0.0,
            -0.0,
            1.0,
            -1.0,
            1e-15,
            -1e-15,
            1e6,
            -1e6,
            3.141592653589793,
            20000.0,
            0.000001,
        ]
        for val in values:
            enc = excess64_encode(val)
            assert len(enc) == 8
            dec = excess64_decode(enc)
            if val == 0.0:
                assert dec == 0.0
            else:
                rel_err = abs(dec - val) / abs(val)
                assert rel_err < 1e-12

    def test_filter_stability_checkerboard_angles(self):
        # Alternating ±90 deg checkerboard
        shape = (4, 4)
        period_nm = np.full(shape, 1000, dtype=np.uint32)
        angle_deg = np.zeros(shape, dtype=np.float64)
        for r in range(4):
            for c in range(4):
                angle_deg[r, c] = 90.0 if (r + c) % 2 == 0 else -90.0
        active = np.ones(shape, dtype=np.bool_)

        design = Design(shape=shape, pitch_nm=20000, period_nm=period_nm, angle_deg=angle_deg, active=active)
        g_filtered = apply_gaussian_filter(design, sigma=1.0, mode="axial")
        assert np.all(np.isfinite(g_filtered.angle_deg))

        b_filtered = apply_bilateral_filter(design, diameter=3, mode="axial")
        assert np.all(np.isfinite(b_filtered.angle_deg))
