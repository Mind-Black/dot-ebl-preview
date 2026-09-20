"""Interactive preview application with headless fallback."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Union

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.preview.renderer import render_preview_to_file


def launch_preview_app(
    design: Design,
    headless: bool = False,
    output_png: Optional[Union[str, Path]] = None,
    preset: str = "corrected",
) -> None:
    """Launch the interactive OpenGL preview window or render headless preview image.

    Args:
        design: Authoritative Design instance.
        headless: If True, skips window initialization and runs entirely headless.
        output_png: Optional path to save a headless optical preview rendering (PNG).
        preset: Optical simulation preset ('corrected', 'glsl-legacy', 'unity-hsv').

    Notes on Interactive OpenGL Viewer (Deferred / Phase 3):
        TODO(OpenGL): Full OpenGL 3.3 Core Profile instance-based interactive renderer.
        The full interactive viewer architecture specified in DEVELOPMENT_PLAN.md (§5, §6) includes:
        1. Coordinated dual-view rendering:
           - Optical appearance view: Per-corner spectral evaluation and interpolation across cell
             quads, computing diffraction orders for 77 wavelength bands (380-760 nm).
           - Geometry view: Real-time rendering of Raith FabricationPlan single-pixel line chords
             with screen-space visible strokes, holopixel circular apertures, and lattice outlines.
        2. Performance architecture for large designs (up to 2.25M cells):
           - Compact instance VBOs (16-24 bytes per active cell: period_nm uint16, angle_rad float32,
             world_pos_xy float32).
           - Viewport frustum culling and tiled streaming to avoid device VRAM exhaustion (<256 MiB).
           - Fast mode toggle (evaluating spectral color at cell centers or visible samples only)
             with indication of approximation status.
        3. Real-time interaction:
           - Orbit camera controls (mouse drag rotate/pan, scroll zoom).
           - Dynamic light source positioning and tilt angles.
           - On-demand high-resolution frame capture.
    """
    if output_png is not None:
        p = render_preview_to_file(design, output_png, preset=preset)
        print(f"Rendered optical preview to {p}")

    if headless:
        return

    # Check for pygame and PyOpenGL availability
    try:
        import pygame
        from OpenGL import GL
    except ImportError:
        print(
            "Note: Interactive OpenGL window requires 'pygame' and 'PyOpenGL'. "
            "Running in headless mode (use --output to save PNG rendered output)."
        )
        return

    # Phase 3 interactive viewer stub / event loop
    print("Launching interactive preview window (press ESC to quit)...")
    pygame.init()
    pygame.display.set_mode((640, 480), pygame.DOUBLEBUF | pygame.OPENGL)
    pygame.display.set_caption("dot-ebl-preview")

    running = True
    clock = pygame.time.Clock()
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

