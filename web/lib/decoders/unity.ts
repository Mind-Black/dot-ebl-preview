/**
 * Legacy Unity HSV decoder matching HologramShader.shader and legacy_unity.py.
 */

import type { DesignModel, RawImageSource } from './types';

export const UNITY_PERIOD_REAL_NM = [1328, 1263, 1225, 1175, 1128, 1066, 1016, 903];

export const UNITY_LASER_HUES = [
  6.0 / 360.0,
  25.0 / 360.0,
  39.0 / 360.0,
  58.0 / 360.0,
  90.0 / 360.0,
  125.0 / 360.0,
  159.0 / 360.0,
  205.0 / 360.0,
];

export function shaderRgbToHsv(r: number, g: number, b: number): [number, number, number] {
  let pX: number, pY: number, pZ: number, pW: number;
  if (b <= g) {
    pX = g;
    pY = b;
    pZ = 0.0;
    pW = -1.0 / 3.0;
  } else {
    pX = b;
    pY = g;
    pZ = -1.0;
    pW = 2.0 / 3.0;
  }

  let qX: number, qY: number, qZ: number, qW: number;
  if (pX <= r) {
    qX = r;
    qY = pY;
    qZ = pZ;
    qW = pX;
  } else {
    qX = pX;
    qY = pY;
    qZ = pW;
    qW = r;
  }

  const d = qX - Math.min(qW, qY);
  const e = 1.0e-10;
  const h = Math.abs(qZ + (qW - qY) / (6.0 * d + e));
  const s = d / (qX + e);
  const v = qX;

  return [h, s, v];
}

export function getUnityGratingNm(h: number, s: number): number {
  if (s < 0.1) {
    return 0;
  }
  if (h > 0.7) {
    return UNITY_PERIOD_REAL_NM[0];
  }

  let closest = 10000000.0;
  let closIdx = 0;
  for (let i = 0; i < 8; i++) {
    const diff = Math.abs(h - UNITY_LASER_HUES[i]);
    // Strict < ensures first entry wins exact ties
    if (diff < closest) {
      closest = diff;
      closIdx = i;
    }
  }
  return UNITY_PERIOD_REAL_NM[closIdx];
}

export function decodeUnityHsv(
  source: RawImageSource,
  userPitchNm?: number,
  minAngleDeg = -10.0,
  maxAngleDeg = 10.0
): DesignModel {
  const { width, height, data } = source;
  const totalCells = width * height;
  const pitchNm = userPitchNm && userPitchNm > 0 ? userPitchNm : 60000;

  const periodNm = new Uint32Array(totalCells);
  const angleDeg = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);
  const appearanceRgb = new Float32Array(totalCells * 3);
  const fallbackIntensity = new Float32Array(totalCells);

  let srcIdx = 0;
  for (let i = 0; i < totalCells; i++) {
    const r = data[srcIdx++] / 255.0;
    const g = data[srcIdx++] / 255.0;
    const b = data[srcIdx++] / 255.0;

    appearanceRgb[i * 3] = r;
    appearanceRgb[i * 3 + 1] = g;
    appearanceRgb[i * 3 + 2] = b;
    fallbackIntensity[i] = (r + g + b) / 3.0 / 5.0;

    const [h, s] = shaderRgbToHsv(r, g, b);
    const gratingNm = getUnityGratingNm(h, s);

    if (gratingNm > 0) {
      active[i] = 1;
      periodNm[i] = gratingNm;
      angleDeg[i] = s * (maxAngleDeg - minAngleDeg) + minAngleDeg;
    } else {
      active[i] = 0;
      periodNm[i] = 0;
      angleDeg[i] = 0;
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
    sourceIdentity: `legacy-unity-hsv:${source.filename}`,
  };
}
