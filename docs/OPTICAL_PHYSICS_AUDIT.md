# Optical Physics & Color Rendering Audit

**Author:** Antigravity (Physicist & Optics Engineer evaluation)  
**Date:** 2026-09-20  
**Target Codebase:** `dot-ebl-preview` (`src/dot_ebl_preview/optics/`, `preview/`, `layout/`)  
**Scope:** Verification of 3D conical diffraction formalisms, periodicities, coordinate conventions, radiometry, polarization, and CIE color rendering.

---

## 1. Executive Summary & Verdict

The optical preview engine in `dot-ebl-preview` implements a **geometric-ray scalar approximation** ported from historical OpenGL (`vertex.txt`) and Unity (`HologramShader.shader`) shaders. 

While the engine reproduces the qualitative angular dispersion of diffraction gratings (wavelengths dispersing across viewing angles), **it is not physically accurate in its present form**. The evaluation identified:
1. **A critical colorimetric defect**: The CIE $XYZ \to \text{sRGB}$ conversion matrix is transposed, which inverts the matrix multiplication in NumPy, corrupts chromaticities across the entire spectrum, inflates red by $>2\times$, and suppresses green by $>50\%$.
2. **Coordinate and grating vector inversion**: Direction cosine equations introduce an asymmetric sign inversion ($\alpha_x \propto +m \sin\theta$ vs. $\alpha_y \propto -m \cos\theta$), reflecting the grating reciprocal vector across $x = -y$ and conflicting with the GDSII fabrication layout.
3. **Unphysical vector addition**: Surface normals are added directly to ray unit vectors (`unit_light + unit_normal`), a dimensionally unphysical relic that only functions because the current normal is $(0, 0, 1)$.
4. **Resonance-domain scalar breakdown**: Operating at $\lambda / \Lambda \sim 0.3 - 0.8$, the grating is in the vector electromagnetic resonance regime. Wood's anomalies, surface plasmon resonances on nickel, TE/TM polarization contrast, and e-beam line morphology are completely neglected; diffraction efficiencies are hardcoded to $1.0$ and $1/15$.
5. **Radiometric & aperture oversimplifications**: The engine treats holopixels as infinite gratings producing delta-rays, omitting the Fraunhofer diffraction envelope of the finite $20\text{ }\mu\text{m}$ aperture ($\Delta\theta \approx 1.9^\circ$), omitting geometric obliquity factors ($\cos\theta_{\text{inc}}, \cos\theta_{\text{diff}}$), and attenuating distance as $1/D$ rather than $1/D^2$.

---

## 2. Detailed Findings by Physical Domain

```
                                [Far-Field Camera / Eye]
                                         ^
                                        /  Diffracted Ray s_m = (alpha_m, beta_m, gamma_m)
                                       /   (Propagating if alpha_m^2 + beta_m^2 <= 1)
   [Directional Light Source]         /
             \                       /
   Ray -L     \      z ^            /
               \       | [Normal n = (0,0,1)]
                v      |          /
             ==================+================== [Substrate z = 0]
                              / \  (Holopixel Cell)
                             /   \
                            /     \ Conical diffraction surface
                           v       \
                          x         y
```

### Finding 1 [P1 — Critical Bug]: Transposed CIE XYZ-to-sRGB Transformation Matrix

* **Locations:**
  * `src/dot_ebl_preview/optics/tables.py:9–18`
  * `src/dot_ebl_preview/optics/engine.py:241`
* **Physics & Mathematics:**
  The international standard IEC 61966-2-1 defines the linear mapping from CIE 1931 $XYZ$ (normalized to $Y = 1.0$ for D65) to linear sRGB as:
  $$\begin{pmatrix} R \\ G \\ B \end{pmatrix} = M_{\text{sRGB}} \begin{pmatrix} X \\ Y \\ Z \end{pmatrix} = \begin{pmatrix} 3.2404542 & -1.5371385 & -0.4985314 \\ -0.9692660 & 1.8760108 & 0.0415560 \\ 0.0556434 & -0.2040259 & 1.0572252 \end{pmatrix} \begin{pmatrix} X \\ Y \\ Z \end{pmatrix}$$
  In `tables.py`, this matrix is initialized with `.T` (transposed):
  ```python
  def XYZ2RGB() -> NDArray[np.float32]:
      return np.array(((3.2404542, -1.5371385, -0.4985314), ...), dtype=np.float32).T
  ```
  In GLSL, matrices are column-major, and `M * v` multiplies column vectors against rows. However, in NumPy, `np.dot(A, x)` computes $\sum_j A_{ij} x_j$ (row-vector dot products). Because the array is transposed, `engine.py` actually computes:
  $$\mathbf{R}_{\text{computed}} = M_{\text{sRGB}}^T \mathbf{X} = \begin{pmatrix} 3.2404542 & -0.9692660 & 0.0556434 \\ -1.5371385 & 1.8760108 & -0.2040259 \\ -0.4985314 & 0.0415560 & 1.0572252 \end{pmatrix} \begin{pmatrix} X \\ Y \\ Z \end{pmatrix}$$
* **Numerical Impact:**
  * **Reference D65 White:** $\mathbf{X}_{\text{D65}} = (0.95047, 1.00000, 1.08883)^T$.
    * Standard IEC 61966-2-1: $\mathbf{R} = (1.000, 1.000, 1.000)^T$ (neutral white).
    * Codebase calculation: $\mathbf{R} = (2.171, 0.193, 0.719)^T \xrightarrow{\text{clip}} (1.000, 0.193, 0.719)^T$ (**distorted to strong reddish-magenta**).
  * **Diffracted $\lambda = 575\text{ nm}$ Line (Yellow-Green):**
    * Correct matrix: $(R, G, B) = (1.383, 0.986, 0.007) \xrightarrow{\text{scaled}} (1.00, 0.71, 0.00)$ (**spectral yellow-green**).
    * Codebase calculation: $(R, G, B) = (2.035, 0.424, -0.260) \xrightarrow{\text{clip}} (1.00, 0.42, 0.00)$ (**brownish orange; green suppressed by 57%**).

---

### Finding 2 [P1 — High]: Conical Diffraction Vector & Coordinate Inversion

* **Locations:**
  * `src/dot_ebl_preview/optics/engine.py:120–121, 153–154, 174–175`
  * `src/dot_ebl_preview/layout/holopixel.py:70–71`
  * `src/dot_ebl_preview/layout/placements.py:66–74`
* **Physics & Mathematics:**
  For a planar reflection grating with grating vector $\mathbf{K} = \frac{2\pi}{\Lambda} \hat{\mathbf{u}}_K$, the tangential direction cosines of diffracted order $m$ under incident unit ray $-\hat{\mathbf{L}}$ are:
  $$\alpha_m = -L_x + m \frac{\lambda}{\Lambda} u_{K, x}, \qquad \beta_m = -L_y + m \frac{\lambda}{\Lambda} u_{K, y}$$
  In `engine.py`:
  ```python
  grating_vec = (math.sin(rad), math.cos(rad), 0.0)
  s_factor = grating_vec[0] / period_m  # sin(theta) / Lambda
  c_factor = grating_vec[1] / period_m  # cos(theta) / Lambda

  alpha_x =  m * wl_m * s_factor - actual_light[0]
  alpha_y = -m * wl_m * c_factor - actual_light[1]
  ```
  The effective grating vector evaluated is:
  $$\hat{\mathbf{u}}_{K, \text{preview}}(\theta) = \begin{pmatrix} \sin\theta \\ -\cos\theta \end{pmatrix}$$
* **Geometric Inconsistencies:**
  1. **Asymmetric sign**: The cosine component has a minus sign while the sine component is positive.
  2. **EBL Layout mismatch**: In `layout/holopixel.py`, unrotated stripes are horizontal (parallel to $X$, normal along $+Y$). In GDSII SREF (`placements.py`), a CCW rotation $\theta$ transforms the normal $(0, 1)^T$ to $(-\sin\theta, \cos\theta)^T$. Thus:
     $$\hat{\mathbf{u}}_{K, \text{preview}}(\theta) = -\hat{\mathbf{u}}_{K, \text{GDS}}(\theta)$$
     Evaluating both $m = \pm 1$ maintains in-plane symmetry at $\theta = 0^\circ$ and $180^\circ$, but inverts the handedness of conical diffraction arcs for general rotation angles.
  3. **Documentation conflict**: The README and `core/model.py` state that angles are measured CCW from $+X$. In contrast, `engine.py` line 119 states rotation is CCW from $+Y$, and the formula anchors the grating vector along $-Y$ at $\theta = 0^\circ$.

---

### Finding 3 [P2 — Medium]: Unphysical Normal Vector Summation (`+ unit_normal`)

* **Location:** `src/dot_ebl_preview/optics/engine.py:146–150`
* **Code:**
  ```python
  actual_light = (unit_light[0] + unit_normal[0], unit_light[1] + unit_normal[1])
  cam_x = unit_cam[0] + unit_normal[0]
  cam_y = unit_cam[1] + unit_normal[1]
  cam_z_sq = max(0.0, 1.0 - cam_x * cam_x - cam_y * cam_y)
  actual_cam = (cam_x, cam_y, math.sqrt(cam_z_sq))
  ```
* **Physics Flaw:**
  Adding the coordinates of a unit normal vector to a unit ray vector ($\hat{\mathbf{L}} + \hat{\mathbf{n}}$) is dimensionally and physically invalid. Direction cosines must be obtained by projecting incident and observation rays onto the local orthonormal surface frame $(\hat{\mathbf{u}}, \hat{\mathbf{v}}, \hat{\mathbf{n}})$.
* **Current State:**
  Because `unit_normal` is hardcoded to $(0, 0, 1)$, `unit_normal[0]` and `unit_normal[1]` are zero, meaning the formula reduces to $(L_x, L_y)$ and $(C_x, C_y)$. However, if surface tilt or non-zero substrate normal rotations are introduced, this expression produces corrupted direction cosines.

---

### Finding 4 [P2 — Physics Limitation]: Resonance-Domain Breakdown & Uncalibrated Efficiencies

* **Location:** `src/dot_ebl_preview/optics/engine.py:58–63, 172`
* **Physics & Mathematics:**
  With periods $\Lambda \in [900, 1300]\text{ nm}$ and visible wavelengths $\lambda \in [380, 760]\text{ nm}$, the parameter ratio is $\lambda / \Lambda \approx 0.3 - 0.8$.
  In this **resonance domain**:
  1. **Scalar diffraction theory fails**: Scalar Fourier/Kirchhoff models cannot predict efficiency when feature dimensions are comparable to the wavelength. Rigorous Coupled-Wave Analysis (RCWA) or Finite-Difference Time-Domain (FDTD) Maxwell solvers are required.
  2. **Wood's Anomalies**: Rayleigh pass-off occurs whenever an order passes from propagating to evanescent:
     $$\lambda_R = \frac{\Lambda}{|m|} \left( \sqrt{1 - \beta_i^2} \pm \alpha_i \right)$$
     This creates sharp spectral intensity discontinuities that are absent in the scalar model.
  3. **Polarization Contrast**: On a lossy metal (nickel: $\varepsilon_{\text{Ni}} \approx -12 + 15i$ at $550\text{ nm}$), TE polarization reflects strongly from ridge boundaries, whereas TM polarization excites Surface Plasmon Polaritons (SPP) at specific angles, generating dark absorption bands. The current model treats all light as unpolarized scalar fields.
  4. **Single-Pixel Line Morphology**: Raith single-pixel lines (`width_nm = 0`) written by an electron beam create relief grooves in nickel with finite width $w \sim 50 - 150\text{ nm}$ and depth $h \sim 100 - 250\text{ nm}$, giving a low duty cycle $\sigma = w / \Lambda \approx 0.05 - 0.15$. 
     * The true efficiency scales with groove density: $\eta \propto \sigma^2 \propto 1 / \Lambda^2$.
     * The codebase treats efficiency as $1.0$ across all periods, ignoring the $\approx 2\times$ intensity difference between $900\text{ nm}$ and $1300\text{ nm}$.
     * Second-order efficiency is hardcoded to $1/15 \approx 0.067$, which is an arbitrary empirical heuristic rather than the true Fourier harmonic of the groove profile.

---

### Finding 5 [P2 — Radiometric Limitation]: Aperture Integration, Holopixel Divergence & Distance Attenuation

* **Location:** `src/dot_ebl_preview/optics/engine.py:83, 144, 180–185`
* **Physics & Mathematics:**
  1. **Finite-Aperture Diffraction Divergence**: Each holopixel has finite width $D = 20\text{ }\mu\text{m}$. By Fraunhofer diffraction, the emitted beam has an intrinsic Airy angular divergence:
     $$\theta_{\text{diff}} \approx 1.22 \frac{\lambda}{D} \approx 1.22 \frac{550\text{ nm}}{20\text{ }\mu\text{m}} \approx 0.0335\text{ rad} \approx 1.92^\circ$$
     At camera distance $D_{\text{cam}} = 66\text{ mm}$, this forms a spot of diameter $w \approx 2.2\text{ mm}$ at the camera plane. The engine treats holopixels as infinite gratings producing zero-divergence rays, and applies a top-hat binary acceptance check against a detector sphere.
  2. **Spectral Sampling Comb**: Because the 77 wavelength bands are discrete points separated by $\Delta\lambda = 5\text{ nm}$, the grating's angular dispersion $\Delta\theta_{\text{step}} = \frac{m \Delta\lambda}{\Lambda \cos\theta}$ causes wavelengths to jump discontinuously into the acceptance cone. When `radius` $< \Delta\theta_{\text{step}} / 2$, spectral dropouts occur.
  3. **Missing Obliquity Factors**: The radiant intensity lacks the standard geometric Lambertian factors:
     $$\cos\theta_{\text{inc}} = \hat{\mathbf{L}} \cdot \hat{\mathbf{n}}, \qquad \cos\theta_{\text{diff}} = \hat{\mathbf{s}}_m \cdot \hat{\mathbf{n}}$$
  4. **Distance Falloff Error**: The acceptance cone radius scales as $1 / D_{\text{cam}}$. For 1D dispersive lines, this reduces captured energy as $1 / D_{\text{cam}}$ rather than adhering to the physical $1 / D_{\text{cam}}^2$ inverse-square law.

---

### Finding 6 [P3 — Colorimetric Approximation]: Gamut Mapping & White Point Normalization

* **Location:** `src/dot_ebl_preview/optics/engine.py:191–239`
* **Color Science Details:**
  1. **Nickel-Tinted White Point:** Division by `light_xyz_acc[1]` normalizes by D65 reflected from specular nickel ($x = 0.3279, y = 0.3441$) rather than pure D65 ($x_n = 0.3127, y_n = 0.3290$). This biases the white point used for desaturation toward warm yellow.
  2. **Abney Effect in $(x, y)$:** Gamut mapping draws a straight line in CIE $1931\text{ }(x, y)$ from the spectral locus toward the white point. Because CIE $xy$ is perceptually non-uniform, straight lines do not follow lines of constant perceived hue (the Abney effect).
  3. **Luminance Distortion under Constant-$Y$ Mapping:** Desaturating saturated spectral colors at constant $Y$ frequently results in linear RGB components exceeding $1.0$ (e.g., $R > 1.4$). The subsequent independent hard clamp `np.clip(rgb, 0.0, 1.0)` distorts both the mapped hue and the perceived luminance.

---

## 3. Prioritized Actionable Items for Developers

```
+---------------------------------------------------------------------------------------+
|                               ACTIONABLE ROADMAP                                      |
+--------------------+------------------------------------------------------------------+
| Phase 1 (Immediate)| Fix transposed XYZ2RGB matrix; correct direction cosines;        |
|                    | remove unit_normal addition; align coordinate docstrings.        |
+--------------------+------------------------------------------------------------------+
| Phase 2 (Medium)   | Add cos(theta) obliquity; replace box-car aperture with smooth   |
|                    | Airy/Gaussian weighting; fix 1/D^2 distance attenuation.         |
+--------------------+------------------------------------------------------------------+
| Phase 3 (Advanced) | Precompute RCWA 2D lookup table for single-pixel nickel lines;   |
|                    | account for TE/TM polarization and Wood's anomalies.             |
+--------------------+------------------------------------------------------------------+
```

### Phase 1: Immediate Bug Fixes (High Impact, Zero Compute Cost)

#### Action 1.1: Remove Transpose in `tables.py`
In `src/dot_ebl_preview/optics/tables.py`, remove `.T` from `XYZ2RGB()`:
```python
# [MODIFY] src/dot_ebl_preview/optics/tables.py
def XYZ2RGB() -> NDArray[np.float32]:
    """CIE XYZ to sRGB conversion matrix (IEC 61966-2-1)."""
    return np.array(
        (
            (3.2404542, -1.5371385, -0.4985314),
            (-0.9692660, 1.8760108, 0.0415560),
            (0.0556434, -0.2040259, 1.0572252),
        ),
        dtype=np.float32,
    )
```

#### Action 1.2: Correct Direction Cosines and Remove `+ unit_normal`
In `src/dot_ebl_preview/optics/engine.py`, replace lines 146–185 with consistent vector direction cosines:
```python
# [MODIFY] src/dot_ebl_preview/optics/engine.py

# 1. Observers and light direction cosines (unit vectors already normalized):
actual_light = (unit_light[0], unit_light[1])
actual_cam = (unit_cam[0], unit_cam[1], unit_cam[2])

# 2. Consistent grating reciprocal vector K matching GDSII SREF rotation:
# Stripes written along X (normal along Y) rotated by angle_deg CCW:
rad = math.radians(angle_deg)
k_x = -math.sin(rad)
k_y = math.cos(rad)

# 3. Tangential direction cosines for order m:
alpha_x = -unit_light[0] + m * (wl_m / period_m) * k_x
alpha_y = -unit_light[1] + m * (wl_m / period_m) * k_y
```

#### Action 1.3: Harmonize Orientation Conventions Across Documentation
Update the docstrings in `src/dot_ebl_preview/optics/engine.py`, `core/model.py`, and `README.md` to explicitly state:
* Grating lines are oriented along $X$ at $\theta = 0^\circ$ (periodic modulation along $+Y$).
* Positive `angle_deg` represents a counterclockwise (CCW) rotation around the $+Z$ axis.

---

### Phase 2: Radiometric & Wave-Optical Refinements (Low Compute Overhead)

#### Action 2.1: Add Geometric Obliquity Weighting
Multiply the diffracted spectral accumulation by incoming and outgoing cosine factors:
```python
cos_inc = max(0.0, unit_light[2])      # dot(unit_light, n) where n = (0,0,1)
cos_diff = max(0.0, alpha_z)           # dot(diff_ray, n)
obliquity = cos_inc * cos_diff
...
xyz_acc += s_xyz * coeff * obliquity
```

#### Action 2.2: Replace Box Filter with Smooth Holopixel Fraunhofer Profile
Instead of a binary step function `dist <= radius`, use a Gaussian or Airy profile representing the finite $20\text{ }\mu\text{m}$ pixel divergence:
```python
# Angular deviation between diffracted ray and camera ray:
dot_val = min(1.0, max(-1.0, alpha_x * actual_cam[0] + alpha_y * actual_cam[1] + alpha_z * actual_cam[2]))
theta_dev = math.acos(dot_val)

# Holopixel diffraction divergence sigma = 0.5 * lambda / D_pixel:
sigma_diff = 0.5 * wl_m / (20e-6)
angular_weight = math.exp(-0.5 * (theta_dev / sigma_diff) ** 2)

xyz_acc += s_xyz * coeff * angular_weight
```
This eliminates discrete 5 nm spectral sampling banding and smoothly blurs pixel diffraction.

#### Action 2.3: Correct Inverse-Square Distance Law
Ensure total collected power scales as $1 / D_{\text{cam}}^2$:
```python
flux_distance_attenuation = 1.0 / (c_len * c_len)
```

---

### Phase 3: Rigorous Vector Electromagnetic Calibration (Phase 3 Roadmap)

#### Action 3.1: Precompute an RCWA Lookup Table for Nickel Single-Pixel Lines
Replace the constant scalar weights (`order_1 = 1.0`, `order_2 = 1/15`) with a 2D interpolated lookup table:
$$\eta_m(\lambda, \Lambda) = \text{RCWA\_Table}(\lambda, \Lambda, \text{depth}=150\text{ nm}, \text{width}=80\text{ nm})$$
Precomputing this table once using an open-source Maxwell solver (such as `S4`, `Meep`, or `RETICOLO`) will provide accurate Rayleigh anomaly cutoffs and period-dependent diffraction efficiency with zero runtime overhead.

---

## 4. Developer Verification & Test Suite

To verify these fixes, add the following automated tests to `tests/test_optics.py`:

```python
# [NEW] tests/test_optics_physics.py
import numpy as np
from dot_ebl_preview.optics.tables import XYZ2RGB
from dot_ebl_preview.optics.engine import simulate_cell_optical_color, OpticalSimParams

def test_d65_white_conversion_neutrality():
    """Verify that CIE D65 white point maps to neutral sRGB (R == G == B)."""
    mat = XYZ2RGB()
    # Normalized D65 XYZ (Y = 1.0)
    d65_xyz = np.array([0.95047, 1.00000, 1.08883], dtype=np.float32)
    rgb = np.dot(mat, d65_xyz)
    np.testing.assert_allclose(rgb, [1.0, 1.0, 1.0], atol=1e-3,
                               err_msg="XYZ2RGB matrix must not be transposed; D65 must yield neutral white.")

def test_monochromatic_spectral_hue_yellow_green():
    """Verify that 1000 nm period at 35 deg incidence produces yellow-green (574 nm)."""
    # 1000 nm period with light at 35 deg diffracts lambda = 1000 * sin(35 deg) = 573.6 nm
    r, g, b = simulate_cell_optical_color(period_nm=1000, angle_deg=0.0)
    assert g > 0.6, f"Expected high green response for 574 nm diffraction, got G={g}"
    assert g >= 0.6 * r, f"Green should be comparable to Red for yellow-green, got R={r}, G={g}"

def test_grating_vector_90deg_extinction():
    """Verify that a 90-degree rotated grating does not diffract in-plane light into the camera."""
    # When light is in the YZ plane and camera is on Z, a grating rotated 90 deg (stripes along Y)
    # diffracts light out of the YZ plane (into +/- X), so it must appear dark in normal viewing.
    r, g, b = simulate_cell_optical_color(period_nm=1000, angle_deg=90.0)
    assert r == 0.0 and g == 0.0 and b == 0.0, "90 deg grating must not diffract into camera along normal."
```
