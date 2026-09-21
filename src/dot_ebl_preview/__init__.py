"""dot_ebl_preview: Combined hologram optical preview and Raith EBL layout application."""

__version__ = "0.1.0"

from dot_ebl_preview.core.model import Design
from dot_ebl_preview.layout.plan import FabricationPlan
from dot_ebl_preview.optics.engine import LightSource, OpticalSimParams
from dot_ebl_preview.api import (
    build_design,
    build_layout,
    export_bundle,
    inspect_design,
)

__all__ = [
    "Design",
    "FabricationPlan",
    "LightSource",
    "OpticalSimParams",
    "build_design",
    "build_layout",
    "export_bundle",
    "inspect_design",
    "__version__",
]

