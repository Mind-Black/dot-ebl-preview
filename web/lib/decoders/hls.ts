/**
 * OpenCV-style HLS decoder for Holtida and Learning Shaders presets.
 * Implements corrected mode matching dot_ebl_preview.io.legacy_hls.
 */

import type { DesignModel, RawImageSource } from './types';

export function roundHalfToEven(val: number): number {
  const floorVal = Math.floor(val);
  const diff = val - floorVal;
  if (Math.abs(diff - 0.5) < 1e-9) {
    return floorVal % 2 === 0 ? floorVal : floorVal + 1;
  }
  return Math.round(val);
}

export function rgbToOpencvHls(
  r8: number,
  g8: number,
  b8: number
): { h: number; l: number; s: number } {
  const r = r8 / 255.0;
  const g = g8 / 255.0;
  const b = b8 / 255.0;

  const maxC = Math.max(r, g, b);
  const minC = Math.min(r, g, b);
  const diff = maxC - minC;

  const lVal = (maxC + minC) / 2.0;

  let sVal = 0.0;
  if (diff > 1e-6) {
    if (lVal <= 0.5) {
      sVal = diff / (maxC + minC);
    } else {
      sVal = diff / (2.0 - maxC - minC);
    }
  }

  let hVal = 0.0;
  if (diff > 1e-6) {
    if (maxC === r) {
      const val = (g - b) / diff;
      hVal = ((val % 6.0) + 6.0) % 6.0;
    } else if (maxC === g) {
      hVal = 2.0 + (b - r) / diff;
    } else {
      hVal = 4.0 + (r - g) / diff;
    }
  }

  let hDeg = hVal * 60.0;
  if (hDeg < 0.0) hDeg += 360.0;

  let hOut = Math.min(180, Math.max(0, Math.round(hDeg / 2.0)));
  if (hOut >= 180) hOut = 0;

  const lOut = Math.min(255, Math.max(0, Math.round(lVal * 255.0)));
  const sOut = Math.min(255, Math.max(0, Math.round(sVal * 255.0)));

  return { h: hOut, l: lOut, s: sOut };
}

// Precalculate 360-entry quantized period lookup table (0.9 to 1.2 µm, 10 nm lattice)
const HLS_PERIOD_LUT_NM = new Uint32Array(360);
for (let i = 0; i < 360; i++) {
  const periodUm = 0.9 + (1.2 - 0.9) * (i / 359.0);
  const discUm = roundHalfToEven(periodUm * 100.0) / 100.0;
  HLS_PERIOD_LUT_NM[i] = Math.round(discUm * 1000.0);
}

export function decodeHls(
  source: RawImageSource,
  preset: 'holtida-ebl' | 'learning-shaders' = 'holtida-ebl',
  userPitchNm?: number,
  applyRadial = true
): DesignModel {
  const { width, height, data } = source;
  const totalCells = width * height;

  const defaultPitch = preset === 'holtida-ebl' ? 20000 : 60000;
  const rotRange = preset === 'holtida-ebl' ? 180.0 : 90.0;
  const pitchNm = userPitchNm && userPitchNm > 0 ? userPitchNm : defaultPitch;

  const periodNm = new Uint32Array(totalCells);
  const angleDeg = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);
  const appearanceRgb = new Float32Array(totalCells * 3);
  const fallbackIntensity = new Float32Array(totalCells);

  const radialMask: boolean[] = [];

  let srcIdx = 0;
  for (let row = 0; row < height; row++) {
    for (let col = 0; col < width; col++) {
      const cellIdx = row * width + col;
      const r = data[srcIdx++];
      const g = data[srcIdx++];
      const b = data[srcIdx++];

      appearanceRgb[cellIdx * 3] = r / 255.0;
      appearanceRgb[cellIdx * 3 + 1] = g / 255.0;
      appearanceRgb[cellIdx * 3 + 2] = b / 255.0;
      fallbackIntensity[cellIdx] = (r + g + b) / (3.0 * 255.0) / 5.0;

      const { h, l, s } = rgbToOpencvHls(r, g, b);

      // Corrected mode activity: active iff 0 < L < 250
      const isActive = l > 0 && l < 250;

      if (isActive) {
        active[cellIdx] = 1;

        // Hue index = 2 * H (0..358)
        const hueIndex = (h * 2) % 360;
        periodNm[cellIdx] = HLS_PERIOD_LUT_NM[hueIndex];

        // Angle: round((S / 255 - 0.5) * rotRange) degrees using NumPy roundHalfToEven
        const sats = (s / 255.0) * 100.0;
        const angle = roundHalfToEven(((sats - 50.0) / 100.0) * rotRange);
        angleDeg[cellIdx] = angle;

        if (h * 2 === 162) {
          radialMask[cellIdx] = true;
        }
      } else {
        active[cellIdx] = 0;
        periodNm[cellIdx] = 0;
        angleDeg[cellIdx] = 0;
      }
    }
  }

  // Radial gradient override for hue-162 cells
  if (applyRadial) {
    const centerY = Math.floor(height / 2) + 50;
    const centerX = Math.floor(width / 2);
    let maxDist = Math.sqrt(centerX * centerX + centerY * centerY);
    if (maxDist === 0) maxDist = 1.0;

    const baseAngle = preset === 'holtida-ebl' ? -15.0 : -5.0;
    const spanAngle = preset === 'holtida-ebl' ? 40.0 : 25.0;

    for (let row = 0; row < height; row++) {
      for (let col = 0; col < width; col++) {
        const cellIdx = row * width + col;
        if (radialMask[cellIdx]) {
          const dist = Math.sqrt((col - centerX) ** 2 + (row - centerY) ** 2);
          angleDeg[cellIdx] = baseAngle + (dist / maxDist) * spanAngle;
        }
      }
    }
  }

  return {
    width,
    height,
    pitchNm,
    periodNm,
    angleDeg,
    active,
    appearanceRgb,
    fallbackIntensity,
    sourceIdentity: `legacy-hls:${preset}:${source.filename}`,
  };
}
