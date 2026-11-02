/**
 * RGB16 Fixed decoder for profile rgb16-fixed-v1.
 * 1 nm period grid, 0.01 degree angle grid offset by 32768 with B-channel activity threshold (B >= 5 is active).
 */

import { MIN_ACTIVE_B } from './rgbIndexed';
import { MIN_PERIOD_NM, MAX_PERIOD_NM, type DesignModel, type RawImageSource } from './types';

export function decodeRgb16Fixed(
  source: RawImageSource,
  userPitchNm?: number
): DesignModel {
  if (source.bitDepth !== 16) {
    throw new Error(`RGB16 fixed profile requires 16-bit image, got ${source.bitDepth}-bit.`);
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

    // Normalized display appearance (for previewing source)
    appearanceRgb[i * 3] = r / 65535.0;
    appearanceRgb[i * 3 + 1] = g / 65535.0;
    appearanceRgb[i * 3 + 2] = b / 65535.0;

    // B channel: any value >= MIN_ACTIVE_B marks an active cell; values below it are discarded.
    // Periods are clamped to [MIN_PERIOD_NM, MAX_PERIOD_NM] (400 nm to 1600 nm).
    if (b >= MIN_ACTIVE_B) {
      active[i] = 1;
      periodNm[i] = Math.max(MIN_PERIOD_NM, Math.min(MAX_PERIOD_NM, r));
      // Signed arithmetic: (G - 32768) / 100.0
      angleDeg[i] = (Number(g) - 32768) / 100.0;
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
    sourceIdentity: `rgb16-fixed-v1:${source.filename}`,
  };
}
