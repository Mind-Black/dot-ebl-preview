# 02 — Core Data Model & Codecs

## The Canonical Physical Data Model

The core architecture separates external image interchange representations from the authoritative physical hologram design. The canonical model stores uncorrupted physical parameters directly in integer nanometres and floating-point rotation angles.

### Python Definition: `Design` Dataclass
File: `src/dot_ebl_preview/core/model.py`

```python
@dataclass(frozen=True)
class Design:
    shape: tuple[int, int]            # (height, width) cell array extents
    pitch_nm: int                     # Lattice cell spacing in integer nanometres (e.g. 20000 nm = 20 µm)
    period_nm: np.ndarray             # 2D uint32 array of grating periods in nanometres
    angle_deg: np.ndarray             # 2D float64 array of grating rotation angles [-90.0, +90.0]
    active: np.ndarray                # 2D bool array: True if cell diffracts, False if substrate
    provenance: dict[str, Any]        # Source metadata, input format, timestamp, file hashes
    fallback_intensity: np.ndarray    # Optional 2D float32 array for non-diffractive substrate tone
```

### TypeScript Definition: `DesignModel` Interface
File: `web/lib/decoders/types.ts`

```typescript
export interface DesignModel {
  width: number;                      // Array width (columns)
  height: number;                     // Array height (rows)
  pitchNm: number;                    // Physical cell pitch in integer nanometres
  periodNm: Uint32Array;              // 1D row-major array of grating periods (nm)
  angleDeg: Float64Array;             // 1D row-major array of grating angles in degrees [-90, +90]
  active: Uint8Array;                 // 1D row-major array: 1 = active, 0 = inactive
  fallbackIntensity?: Float32Array;   // Optional fallback grayscale for inactive cells
  sourceIdentity: string;             // File or preset identifier for cache invalidation
  layer?: number;                     // Target GDSII layer number (default: 1)
  dose?: number;                      // Fabrication dose factor (default: 1.0)
  regionMasks?: Record<string, Uint8Array>; // Region segmentations (e.g., area, perimeter)
  artifactMetadata?: Record<string, unknown>; // Operation history and pipeline provenance
}
```

---

## Coordinate System & Physical Alignment

```
           Image Coordinates (r, c)                   Fabrication Physical Space (nm)
       0 ---------------------> +X (cols)                -Y (nm) ^
       |  (0,0)         (0, W-1)                                 |
       |                                                         |  Cell (r, c) center:
       |                                                         |  x = (c + 0.5) * P
       |  (H-1, 0)      (H-1, W-1)         ----------------------+----------------------> +X (nm)
       v                                                         |  y = -(r + 0.5) * P
       +Y (rows)                                                 |
                                                                 v +Y (nm)
```

1. **Cell Indexing**:
   - Row $r \in [0, H-1]$ increases downward (+Y in image space).
   - Column $c \in [0, W-1]$ increases rightward (+X in image space).
   - Total cell count $N = H \times W$.
   - 1D linear array index: $\text{idx} = r \times W + c$.

2. **Physical Cell Centers**:
   For cell pitch $P$:
   $$\begin{aligned}
   x_{\text{center}} &= (c + 0.5) \cdot P \\
   y_{\text{center}} &= -(r + 0.5) \cdot P
   \end{aligned}$$

3. **Centered Preview Offset**:
   When centering the design at the origin:
   $$x_{\text{world}} = \left(c + 0.5 - \frac{W}{2}\right) \cdot P, \quad y_{\text{world}} = -\left(r + 0.5 - \frac{H}{2}\right) \cdot P$$

4. **Half-Away-From-Zero Quantization**:
   To prevent platform drift across JavaScript, Python, MATLAB, and C runtimes:
   $$\text{round}(x) = \begin{cases} \lfloor x + 0.5 \rfloor & \text{if } x \ge 0 \\ \lceil x - 0.5 \rceil & \text{if } x < 0 \end{cases}$$

---

## Supported Input Interchange Formats

### 1. `RGBA continuous` (Recommended Direct Physical Profile)
- **Files**: `web/lib/decoders/rgbaContinuous.ts`, `src/dot_ebl_preview/core/encoding.py`
- **Mapping**:
  - **Red & Green (16-bit Period)**: $\text{raw16} = R \times 256 + G$.
    $$\text{period\_nm} = \text{min\_period} + \frac{\text{raw16}}{65535} \times (\text{max\_period} - \text{min\_period})$$
    Defaults: $\text{min} = 400\,\text{nm}, \text{max} = 1600\,\text{nm}$.
  - **Blue (8-bit Rotation Angle)**:
    $$\text{angle\_deg} = \text{min\_angle} + \frac{B}{255} \times (\text{max\_angle} - \text{min\_angle})$$
    Defaults: $\text{min} = -90.0^\circ, \text{max} = +90.0^\circ$.
  - **Alpha (8-bit Activity Mask)**: Active if $A \ge 128$.

### 2. `rgb8-indexed-v1`
- **Specification**: Fixed 256-entry lookup table mapping 8-bit index values to discrete pairs of $(\text{period\_nm}, \text{angle\_deg})$.
- **Usage**: Archival compatibility with restricted-palette micro-lithography runs.

### 3. `rgb16-fixed-v1`
- **Specification**: 16-bit per channel RGB PNG / TIFF.
- **Mapping**: Channel R encodes period in direct nanometres ($[0, 65535]\,\text{nm}$); Channel G encodes rotation angle in fixed centidegrees ($[0, 18000] \to [-90.00^\circ, +90.00^\circ]$); Channel B encodes activity threshold.

### 4. Legacy Holtida HLS (`holtida-ebl`)
- **Files**: `web/lib/decoders/hls.ts`, `src/dot_ebl_preview/io/legacy_hls.py`
- **Historical Source**: OpenCV HLS representation from legacy Holtida software.
- **Default Pitch**: $20,000\,\text{nm}$ ($20\,\mu\text{m}$).
- **Mapping**:
  - Hue ($H \in [0, 179]$): Angle span of $180^\circ$.
  - Lightness ($L \in [0, 255]$): Activity gating (active if $L > 25$).
  - Saturation ($S \in [0, 255]$): Period span ($900\,\text{nm}$ to $1200\,\text{nm}$).

### 5. Legacy Learning Shaders HLS (`learning-shaders`)
- **Historical Source**: Academic educational shader implementation.
- **Default Pitch**: $60,000\,\text{nm}$ ($60\,\mu\text{m}$).
- **Mapping**: Angle span restricted to $90^\circ$ ($[-5^\circ, +20^\circ]$).

### 6. Legacy Unity HSV (`unity-hsv`)
- **Files**: `web/lib/decoders/unity.ts`, `src/dot_ebl_preview/io/images.py`
- **Historical Source**: Unity `HologramShader.shader`.
- **Mapping**: Floating-point Hue $[0, 1)$ mapped to continuous rotation angle; Value $V$ mapped to grating period; Saturation $S$ acting as cell visibility mask.

### 7. NumPy Compressed Archive (`.npz`)
- **Files**: `web/lib/io/npzParser.ts`, `src/dot_ebl_preview/io/images.py`
- **Security**: Parsed without Python pickle (`allow_pickle=False` in Python; pure-JS ZIP parser in Web).
- **Archive Contents**:
  - `period_nm`: 2D `uint32` array.
  - `angle_deg`: 2D `float64` array.
  - `active`: 2D `bool_` or `uint8` array.
  - `metadata_json`: 1D UTF-8 JSON string array storing physical pitch (`pitch_nm`), coordinate provenance, and versioning.
  - `mask_area`, `mask_perimeter`: Optional region masks.
