"""Coordinate system, grid geometry, and physical extents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
import numpy as np
from numpy.typing import NDArray

from dot_ebl_preview.core.encoding import round_half_away_from_zero


@dataclass(frozen=True)
class Extents:
    """Physical bounding box in fabrication coordinates (nanometres)."""
    x_min_nm: int
    x_max_nm: int
    y_min_nm: int
    y_max_nm: int

    @property
    def width_nm(self) -> int:
        return self.x_max_nm - self.x_min_nm

    @property
    def height_nm(self) -> int:
        return self.y_max_nm - self.y_min_nm


def cell_center_nm(row: int, col: int, pitch_nm: int, snap: bool = True) -> Tuple[int, int]:
    """Calculate the fabrication center coordinates (x, y) for cell (row, col) in nanometres.

    Formula:
      x = (col + 0.5) * pitch_nm
      y = -(row + 0.5) * pitch_nm

    When pitch_nm is odd, (col + 0.5)*pitch_nm lies on a half-nanometre.
    If snap=True, rounds half-away-from-zero to integer nm.
    """
    x_exact = (col + 0.5) * pitch_nm
    y_exact = -(row + 0.5) * pitch_nm
    if snap:
        return int(round_half_away_from_zero(x_exact)), int(round_half_away_from_zero(y_exact))
    return int(x_exact), int(y_exact)


def grid_centers_nm(height: int, width: int, pitch_nm: int) -> Tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Compute 2D arrays of fabrication center coordinates (X, Y) in nanometres."""
    rows, cols = np.indices((height, width), dtype=np.int64)
    x_exact = (cols + 0.5) * pitch_nm
    y_exact = -(rows + 0.5) * pitch_nm
    x_snapped = round_half_away_from_zero(x_exact).astype(np.int64)
    y_snapped = round_half_away_from_zero(y_exact).astype(np.int64)
    return x_snapped, y_snapped


def design_extents_nm(height: int, width: int, pitch_nm: int) -> Extents:
    """Compute overall physical bounding box for the entire array (including borders).

    Row 0 to height-1, Col 0 to width-1:
      x extends from 0 to width * pitch_nm
      y extends from -height * pitch_nm to 0
    """
    return Extents(
        x_min_nm=0,
        x_max_nm=width * pitch_nm,
        y_min_nm=-height * pitch_nm,
        y_max_nm=0,
    )


def centered_preview_offset_nm(height: int, width: int, pitch_nm: int) -> Tuple[float, float]:
    """Preview centering translation offset: (-W*pitch/2, +H*pitch/2)."""
    return (-width * pitch_nm / 2.0, height * pitch_nm / 2.0)
