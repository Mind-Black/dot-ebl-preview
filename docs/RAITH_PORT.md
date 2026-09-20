# Raith_GDSII Python translation scope

Upstream: [University of Alberta nanoFAB Raith_GDSII](https://github.com/ahryciw/Raith_GDSII), commit `946888a8aa6b634cf2e4db3164188acc5f2f7f1e`, retrieved 2026-09-20. The four original MATLAB classes and LICENSE are preserved under `reference/Raith_GDSII/`. This is a reference snapshot, not a Python implementation or runtime dependency. The [upstream class documentation](https://raith-gdsii.readthedocs.io/en/latest/Raith_library.html) distinguishes native `.csf` and plain `.gds` output.

## Initial port boundary

The user's follow-up replaces the original rectangular polygons with Raith single-pixel lines. Upstream specifies `Raith_element('path', layer, uv, 0, DF)` for this purpose: [path element documentation](https://raith-gdsii.readthedocs.io/en/latest/Raith_element.html#path-element). Each stripe is one separate two-endpoint path; this is not the Raith `dot` primitive. Rotated/translated SREFs still place reusable holopixels. No polygon or native circle primitive is required in the initial production port. Translation covers the dependency closure below, not all of Raith_GDSII.

| Upstream source | Python work | Why required |
|---|---|---|
| `Raith_element.m:221`, `:305`, `:481`, `:610` | Path/SREF construction, typed validation, finite values, nm quantization, path endpoint count, width 0, layer/DF rules | Single-pixel lines and placements |
| `Raith_structure.m:75`, `:85`, `:105` | Named ordered structures, name validation, reference list | Reusable cells and hologram/root hierarchy |
| `Raith_library.m` constructor, setters, append, writegds | Ordered library, unique names, missing-reference checks, native/plain output | Complete layout generation |
| `Raith_library.m` rot/trans/refl/scale | Transformation semantics and composition | Correct rotation and coordinate inspection |
| `Raith_library.m` writerec + nested excess64 | Big-endian records, padding, GDS real8 conversion | Actual Python binary writer |
| `Raith_library.m` writehead/writebeginstruct/writeelement/writeendstruct/writeendlib | Header, units, PATH and SREF record branches | Export dependency closure |
| `Raith_library.m` DFint | Dose-to-DATATYPE encoding | Preserve layer 1 / datatype 1000 |

Initial SREF supports translation, rotation, positive magnification and reflection, including defaults; using the full small transform contract prevents future incompatible model changes. Design generation normally uses magnification 1 and no reflection. The writer exposes a capability registry with supported element and dialect IDs. Requests for unported elements fail before any final output is created.

## Semantics that need tests, not a mechanical syntax rewrite

- Upstream coordinates are µm, rounded to a 1 nm grid by element setters; XY records are signed int32 nm. UNITS values are `1e-3` and `1e-9` (database unit in user units and metres). Python public units must be explicit. Match MATLAB half-away-from-zero rounding at positive and negative ties; do not use NumPy's default ties-to-even for this port.
- MATLAB uv arrays are 2×N and column-major reshaping emits interleaved x,y pairs. Python uses N×2 and explicitly emits those pairs. Test a non-symmetric diagonal path so an accidental transpose cannot pass.
- Native layers are integers 0–63. Path dose is nonnegative and at most 17797.5; upstream first rounds dose to 0.001 and then rounds values above 30 to 0.5. DATATYPE is `1000*DF` up to 30, otherwise `30000 + 2*(DF-30)`. DF=1 gives 1000. Upper values require the upstream unsigned 16-bit payload behavior; test values above 32767 against target readers rather than assuming signed standard-GDS interpretation.
- Ordinary `.gds` path output still carries this numeric DATATYPE; plain dialect is not a promise that every reader interprets it as a dose or displays zero-width geometry. Keep native dose meaning and generic GDS datatype separate in the public model; initial application default maps DF 1 to 1000 in both dialects. Single-pixel line dose must be qualified independently of the old area exposure recipe.
- GDS real8 is sign/excess-64 exponent/base-16 fraction, not IEEE double. Include zero, sign, small units, rotation, magnification, exponent boundaries and nonfinite rejection tests. Preserve upstream truncation/normalization behavior where fixtures prove it.
- Records have big-endian length/type/data headers and even byte padding. Enforce length limits and int32 coordinate bounds before packing. Each stripe writes PATH (0900), LAYER (0d02), DATATYPE (0e02), WIDTH (0f03) with integer zero, XY (1003) with exactly two distinct endpoints, then ENDEL (1100). Match the upstream explicit zero WIDTH record, not a viewer-specific omission. Do not add path extensions, close the path, or substitute a narrow polygon. Reject nonzero widths in the initial capability contract; generic finite/negative-width paths can be enabled later with their own tests.
- Upstream SREF emits STRANS before MAG/ANGLE when needed, uses reflection bit 32768, and emits both MAG and ANGLE if either differs from its default. Match record order and transform composition. Negative coordinates and nonzero angles need round-trip tests.
- Upstream structure names allow up to 127 characters and sanitize invalid characters. Generate conservative ASCII names (≤32 characters for portable application output) with stable hashes; retain a readable name map. Validate collisions after sanitization and protect references from later renaming.
- Reject reference cycles as well as missing references; maintain efficient name/reference dictionaries. Batch validation and immutable snapshots replace MATLAB's mutable handles/global `checkdata` bypass. This is an explicit API improvement, not a missing feature.
- Preserve original local chord centerlines, snap endpoints once at the defined boundary, and use references for rotations. Do not round the rotation to integers after filtering. Reference-transformed endpoints may not lie on integer coordinates until a downstream flatten operation; distinguish local database-grid error from transformed/flattened error. Skip/count a chord whose endpoints collapse at the nm grid; never emit a dot accidentally.

Use a small independent record inspector plus a mature GDS reader as test tools. Pin the independent reader version. The production export must actually use the translated Raith serializer, not delegate to gdsfactory/gdstk and rename the result.

## Deferred feature inventory and expansion order

All following source remains available in the pinned snapshot. Each future entry needs constructor validation, rendering/geometry semantics where relevant, native records, plain fallback where relevant, MATLAB fixtures and target-reader tests before its capability is advertised.

| Feature group | Source entry points | Future implementation |
|---|---|---|
| Polygons, general paths and dots | Element polygon/path/dot branches, plotpathwidth, library writeelement | Polygon closure, finite/negative-width semantics and width-rendering, polylines, scalar/per-dot DF; initial zero-width two-endpoint path support is already in scope |
| Array references | Element aref, library aref writing and hierarchy plotting | COLROW and spacing; explicitly distinguish Raith array interpretation from standard GDS under rotations/reflections; optimize repeated regular patterns only after qualification |
| Curves | Element arc/circle/ellipse, renderplot; library curved-record branches | Native record type 86; filled/line/ring variants, angular encoding, vertex/tessellation settings; plain conversion to polygons/paths |
| FBMS | Element fbmspath/fbmscircle; library record type 88 | Curvature flags and width; native exposure semantics and plain fallback |
| Text | Element rendertext and embedded chars/font tables | Preserve simply-connected glyph polygons, alignment, spacing, rotation; no substitution with GDS TEXT that changes exposure geometry |
| Plotting | Element plot/plotedges/renderplot/RaithDF; structure and library plot/plotedges | Matplotlib adapters, dose colors, filled/edge views, hierarchical transforms and unresolved-reference markers |
| Position lists | Entire Raith_positionlist class | Properties/library path, append, plot/plotedges, plotWA/plotWF, centre with matrix-copy, shift, writepls, plotchip/checkposlist/alllayers; preserve mm chip/origin versus µm writefield/working-area units |

Initial application geometry inspection draws FabricationPlan centerlines with an explicit display stroke without porting all MATLAB plotting helpers. Future modules plug into separate element validation, geometry rendering, native serialization and plain conversion registries. Unknown types are rejected, never dropped or silently flattened. Preserve upstream fixture scripts, source checksums and per-method status (`reference-only`, `translated`, `verified`) so “available for future translation” has a concrete artifact.

## Provenance and license handling

Retain upstream author and source notices and the supplied MPL-2.0 LICENSE alongside the snapshot and translated files; mark modified/translated files and keep the port isolated for clear provenance. This is the implementation's attribution plan, not a legal opinion about all distribution scenarios. Follow the [upstream citation guidance](https://raith-gdsii.readthedocs.io/en/latest/introduction.html#citing-raith-gdsii) for scientific publications using the toolbox. A manifest records the exact source revision and hashes; never update the reference snapshot implicitly during a port.
