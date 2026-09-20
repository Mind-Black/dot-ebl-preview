"""Single-pixel circular-envelope holopixel geometry generator."""

from __future__ import annotations

import math
from typing import List, Tuple
import numpy as np

from dot_ebl_preview.core.encoding import round_half_away_from_zero
from dot_ebl_preview.raith.elements import PathElement


def generate_holopixel_stripes(
    pitch_nm: int,
    period_nm: int,
    layer: int = 1,
    dose: float = 1.0,
) -> Tuple[List[PathElement], int]:
    """Generate circular-envelope single-pixel grating stripes (width 0 nm) for a single holopixel.

    Stripe center lattice:
      y = -pitch_nm / 2 + period_nm / 2 + k * period_nm
      Within radius R = pitch_nm / 2.0
      x_max = sqrt(R^2 - y^2)

    Endpoints are snapped to integer nanometres. Zero-length chords or endpoints collapsing
    to the same nm coordinate are skipped and counted.

    Returns:
      (paths, skipped_degenerate_count)
    """
    if pitch_nm <= 0 or period_nm <= 0:
        raise ValueError(f"pitch_nm and period_nm must be positive, got pitch={pitch_nm}, period={period_nm}")

    r_radius = pitch_nm / 2.0
    r_sq = r_radius * r_radius

    # Determine stripe indices deterministically
    # Start at y_0 = -pitch_nm / 2.0 + period_nm / 2.0
    y_start = -r_radius + (period_nm / 2.0)
    # Number of stripes: while y <= r_radius
    paths: List[PathElement] = []
    skipped_count = 0

    # Calculate k_min and k_max analytically
    # y = y_start + k * period_nm
    # -r_radius <= y <= r_radius
    k_min = int(math.ceil((-r_radius - y_start) / period_nm))
    k_max = int(math.floor((r_radius - y_start) / period_nm))

    for k in range(k_min, k_max + 1):
        y_exact = y_start + k * period_nm
        if abs(y_exact) > r_radius:
            continue

        # Guard against floating-point roundoff before sqrt
        diff = r_sq - (y_exact * y_exact)
        if diff < 0.0 and diff > -1e-7:
            diff = 0.0
        elif diff < 0.0:
            continue

        x_max_exact = math.sqrt(diff)

        # Snap coordinates to integer nm with half-away-from-zero rounding
        x_snap = int(round_half_away_from_zero(x_max_exact))
        y_snap = int(round_half_away_from_zero(y_exact))

        # Check for degenerate chord: endpoints must be distinct
        p1 = (-x_snap, y_snap)
        p2 = (x_snap, y_snap)

        if p1 == p2 or x_snap == 0:
            skipped_count += 1
            continue

        paths.append(
            PathElement(
                layer=layer,
                vertices_nm=[p1, p2],
                width_nm=0,
                df=dose,
            )
        )

    return paths, skipped_count
