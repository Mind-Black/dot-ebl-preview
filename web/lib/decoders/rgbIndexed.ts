/**
 * RGB8 Indexed decoder for profile rgb8-indexed-v1.
 * Discrete lookup tables for period and angle with B-channel activity threshold (B >= 5 is active).
 */

import { MIN_PERIOD_NM, MAX_PERIOD_NM, type DesignModel, type RawImageSource } from './types';

export const RGB8_PERIOD_LUT_NM: number[] = Array.from({ length: 31 }, (_, r) => 900 + 10 * r);
export const RGB8_ANGLE_LUT_DEG: number[] = Array.from({ length: 181 }, (_, g) => g - 90.0);

/** B-channel values below this threshold mark a cell as inactive (discarded). */
export const MIN_ACTIVE_B = 5;

export function decodeRgb8Indexed(
  source: RawImageSource,
  userPitchNm?: number
): DesignModel {
  if (source.bitDepth !== 8) {
    throw new Error(`RGB8 indexed profile requires 8-bit image, got ${source.bitDepth}-bit.`);
  }

  const { width, height, data } = source;
  const totalCells = width * height;
  const pitchNm = userPitchNm && userPitchNm > 0 ? userPitchNm : 20000;

  const periodNm = new Uint32Array(totalCells);
  const angleDeg = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);
  const appearanceRgb = new Float32Array(totalCells * 3);

  let srcIdx = 0;
  for (let i = 0; i < totalCells; i++) {
    const r = data[srcIdx++];
    const g = data[srcIdx++];
    const b = data[srcIdx++];

    appearanceRgb[i * 3] = r / 255.0;
    appearanceRgb[i * 3 + 1] = g / 255.0;
    appearanceRgb[i * 3 + 2] = b / 255.0;

    // B channel: any value >= MIN_ACTIVE_B marks an active cell; values below it are discarded.
    if (b >= MIN_ACTIVE_B) {
      if (r >= RGB8_PERIOD_LUT_NM.length) {
        const row = Math.floor(i / width);
        const col = i % width;
        throw new Error(
          `R channel index ${r} at cell (${row}, ${col}) exceeds period LUT size (${RGB8_PERIOD_LUT_NM.length}).`
        );
      }
      if (g >= RGB8_ANGLE_LUT_DEG.length) {
        const row = Math.floor(i / width);
        const col = i % width;
        throw new Error(
          `G channel index ${g} at cell (${row}, ${col}) exceeds angle LUT size (${RGB8_ANGLE_LUT_DEG.length}).`
        );
      }

      active[i] = 1;
      periodNm[i] = Math.max(MIN_PERIOD_NM, Math.min(MAX_PERIOD_NM, RGB8_PERIOD_LUT_NM[r]));
      angleDeg[i] = RGB8_ANGLE_LUT_DEG[g];
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
    fallbackIntensity: undefined,
    sourceIdentity: `rgb8-indexed-v1:${source.filename}`,
  };
}
