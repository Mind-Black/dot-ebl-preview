/**
 * Unified design decoding and parameter statistics extraction.
 */

import { decodeHls } from './hls';
import { decodeUnityHsv } from './unity';
import { decodeRgb8Indexed } from './rgbIndexed';
import { decodeRgb16Fixed } from './rgbFixed';
import { decodeRgbaContinuous, type RgbaContinuousOptions } from './rgbaContinuous';
import type { DesignModel, InterpretationFormat, ParameterStats, RawImageSource } from './types';

export * from './types';
export * from './hls';
export * from './unity';
export * from './rgbIndexed';
export * from './rgbFixed';
export * from './rgbaContinuous';

export function decodeDesign(
  source: RawImageSource,
  format: InterpretationFormat,
  pitchNm?: number,
  rgbaOptions?: RgbaContinuousOptions
): DesignModel {
  switch (format) {
    case 'RGBA continuous':
      return decodeRgbaContinuous(source, rgbaOptions, pitchNm);
    case 'Holtida legacy HLS':
      return decodeHls(source, 'holtida-ebl', pitchNm);
    case 'Learning Shaders HLS':
      return decodeHls(source, 'learning-shaders', pitchNm);
    case 'Unity HSV':
      return decodeUnityHsv(source, pitchNm);
    case 'RGB8 indexed':
      return decodeRgb8Indexed(source, pitchNm);
    case 'RGB16 fixed':
      return decodeRgb16Fixed(source, pitchNm);
    default:
      throw new Error(`Unsupported image interpretation format: ${format}`);
  }
}

export function computeParameterStats(design: DesignModel): ParameterStats {
  const { width, height, pitchNm, periodNm, angleDeg, active } = design;
  const totalCells = width * height;

  let activeCells = 0;
  const periodCounts = new Map<number, number>();
  const angleCounts = new Map<number, number>();

  let minPeriod = Infinity;
  let maxPeriod = -Infinity;
  let minAngle = Infinity;
  let maxAngle = -Infinity;

  for (let i = 0; i < totalCells; i++) {
    if (active[i]) {
      activeCells++;
      const p = periodNm[i];
      const a = Math.round(angleDeg[i] * 100) / 100; // group close angles for table/hist

      if (p < minPeriod) minPeriod = p;
      if (p > maxPeriod) maxPeriod = p;
      if (a < minAngle) minAngle = a;
      if (a > maxAngle) maxAngle = a;

      periodCounts.set(p, (periodCounts.get(p) || 0) + 1);
      angleCounts.set(a, (angleCounts.get(a) || 0) + 1);
    }
  }

  const uniquePeriods = Array.from(periodCounts.entries())
    .map(([periodNm, count]) => ({ periodNm, count }))
    .sort((a, b) => a.periodNm - b.periodNm);

  const uniqueAngles = Array.from(angleCounts.entries())
    .map(([angleDeg, count]) => ({ angleDeg, count }))
    .sort((a, b) => a.angleDeg - b.angleDeg);

  const fillFactor = totalCells > 0 ? activeCells / totalCells : 0;
  const widthMm = (width * pitchNm) * 1e-6;
  const heightMm = (height * pitchNm) * 1e-6;

  return {
    totalCells,
    activeCells,
    fillFactor,
    widthMm,
    heightMm,
    uniquePeriods,
    uniqueAngles,
    minPeriodNm: activeCells > 0 ? minPeriod : 0,
    maxPeriodNm: activeCells > 0 ? maxPeriod : 0,
    minAngleDeg: activeCells > 0 ? minAngle : 0,
    maxAngleDeg: activeCells > 0 ? maxAngle : 0,
  };
}
