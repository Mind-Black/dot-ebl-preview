/**
 * Decoder and masked bilateral filter for RGBA continuous parameter profile.
 *
 * Contract:
 * - Channels: 4 (RGBA)
 * - Bit depth: 8-bit (uint8) or 16-bit (uint16)
 * - R: Continuous linear mapping across [min_period_nm, max_period_nm] (default 400..1600 nm)
 * - G: Continuous linear mapping across [min_angle_deg, max_angle_deg] (default -90..+90 deg)
 * - B: Reserved / ignored
 * - A: Thresholded at 50% opacity (128 for 8-bit, 32768 for 16-bit)
 * - Masked bilateral filter:
 *   * Valid-only masking: inactive cells are never sampled
 *   * Period: scalar bilateral filter
 *   * Angle: axial bilateral filter respecting 180° symmetry with nearest-branch lift
 */

import type { DesignModel, RawImageSource } from './types';

export interface RgbaContinuousOptions {
  minPeriodNm?: number;
  maxPeriodNm?: number;
  minAngleDeg?: number;
  maxAngleDeg?: number;
  applyFilter?: boolean;
  filterDiameter?: number;
  filterSigmaColorPeriod?: number;
  filterSigmaColorAngle?: number;
  filterSigmaSpace?: number;
  roundIntegerAngles?: boolean;
  roundPeriod50Nm?: boolean;
}

/**
 * Round half-away-from-zero (MATLAB/C99 style rounding matching Python round_half_away_from_zero).
 * For x >= 0: floor(x + 0.5)
 * For x < 0:  ceil(x - 0.5)
 */
export function roundHalfAwayFromZero(val: number): number {
  return (val >= 0 ? Math.floor(val + 0.5) : Math.ceil(val - 0.5)) + 0;
}

export function liftToNearestBranch(thetaAxial: number, thetaOrig: number): number {
  const base = ((thetaAxial + 90.0) % 180.0 + 180.0) % 180.0 - 90.0;
  const kCenter = Math.round((thetaOrig - base) / 180.0);
  let bestBranch = base;
  let bestDist = Infinity;

  for (const k of [kCenter - 1, kCenter, kCenter + 1]) {
    const cand = base + k * 180.0;
    const dist = Math.abs(cand - thetaOrig);
    if (dist < bestDist - 1e-9) {
      bestDist = dist;
      bestBranch = cand;
    } else if (Math.abs(dist - bestDist) <= 1e-9) {
      if (cand < bestBranch) {
        bestBranch = cand;
      }
    }
  }
  return bestBranch;
}

export function applyMaskedBilateralFilter(
  width: number,
  height: number,
  periodNm: Uint32Array,
  angleDeg: Float64Array,
  active: Uint8Array,
  diameter = 3,
  sigmaColorPeriod = 50.0,
  sigmaColorAngle = 10.0,
  sigmaSpace = 100.0,
  filterPeriod = true,
  filterAngle = true
): { periodNm: Uint32Array; angleDeg: Float64Array } {
  if (diameter <= 1 || (!filterPeriod && !filterAngle)) {
    return { periodNm: new Uint32Array(periodNm), angleDeg: new Float64Array(angleDeg) };
  }

  const radius = Math.floor(diameter / 2);
  const outPeriod = new Uint32Array(periodNm);
  const outAngle = new Float64Array(angleDeg);

  // Precompute spatial weights
  const spatialKernel: number[][] = [];
  const twoSigmaSpaceSq = 2.0 * sigmaSpace * sigmaSpace;
  for (let dy = -radius; dy <= radius; dy++) {
    const row: number[] = [];
    for (let dx = -radius; dx <= radius; dx++) {
      row.push(Math.exp(-(dx * dx + dy * dy) / twoSigmaSpaceSq));
    }
    spatialKernel.push(row);
  }

  const twoSigmaColorPeriodSq = 2.0 * sigmaColorPeriod * sigmaColorPeriod;
  const twoSigmaColorAngleSq = 2.0 * sigmaColorAngle * sigmaColorAngle;

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const idx = r * width + c;
      if (!active[idx]) continue;

      const centerP = periodNm[idx];
      const centerA = angleDeg[idx];

      let sumWPeriod = 0;
      let sumPeriodVal = 0;

      let sumWAngle = 0;
      let sinSum = 0;
      let cosSum = 0;

      for (let dy = -radius; dy <= radius; dy++) {
        const nr = r + dy;
        if (nr < 0 || nr >= height) continue;
        const kRow = dy + radius;

        for (let dx = -radius; dx <= radius; dx++) {
          const nc = c + dx;
          if (nc < 0 || nc >= width) continue;
          const kCol = dx + radius;

          const nIdx = nr * width + nc;
          if (!active[nIdx]) continue;

          const wSpace = spatialKernel[kRow][kCol];
          const nP = periodNm[nIdx];
          const nA = angleDeg[nIdx];

          if (filterPeriod) {
            const diffP = nP - centerP;
            const wColorP = Math.exp(-(diffP * diffP) / twoSigmaColorPeriodSq);
            const wP = wSpace * wColorP;
            sumWPeriod += wP;
            sumPeriodVal += wP * nP;
          }

          if (filterAngle) {
            // Axial angle difference modulo 180
            const diffA = ((nA - centerA + 90.0) % 180.0 + 180.0) % 180.0 - 90.0;
            const wColorA = Math.exp(-(diffA * diffA) / twoSigmaColorAngleSq);
            const wA = wSpace * wColorA;
            sumWAngle += wA;
            const rad2 = (2.0 * nA * Math.PI) / 180.0;
            sinSum += wA * Math.sin(rad2);
            cosSum += wA * Math.cos(rad2);
          }
        }
      }

      if (filterPeriod) {
        if (sumWPeriod > 1e-9) {
          outPeriod[idx] = Math.round(sumPeriodVal / sumWPeriod);
        } else {
          outPeriod[idx] = centerP;
        }
      }

      if (filterAngle) {
        if (sumWAngle > 1e-9) {
          const mag = Math.hypot(sinSum, cosSum);
          if (mag >= 1e-6) {
            const th2 = (Math.atan2(sinSum, cosSum) * 180.0) / Math.PI;
            outAngle[idx] = liftToNearestBranch(th2 / 2.0, centerA);
          } else {
            outAngle[idx] = centerA;
          }
        } else {
          outAngle[idx] = centerA;
        }
      }
    }
  }

  return { periodNm: outPeriod, angleDeg: outAngle };
}

export function decodeRgbaContinuous(
  source: RawImageSource,
  options?: RgbaContinuousOptions,
  pitchNm = 20000
): DesignModel {
  if(source.channels === 3){
    const data=source.bitDepth===16?new Uint16Array(source.width*source.height*4):new Uint8Array(source.width*source.height*4);
    for(let i=0;i<source.width*source.height;i++){data.set(source.data.subarray(i*3,i*3+3),i*4);data[i*4+3]=source.bitDepth===16?65535:255;}
    source={...source,channels:4,data};
  }
  if (source.channels !== 4) {
    throw new Error(
      `RGBA continuous format requires 4-channel image (RGBA), but image has ${source.channels} channels.`
    );
  }

  const minPeriod = options?.minPeriodNm ?? 400.0;
  const maxPeriod = options?.maxPeriodNm ?? 1600.0;
  const minAngle = options?.minAngleDeg ?? -90.0;
  const maxAngle = options?.maxAngleDeg ?? 90.0;
  const applyFilter = options?.applyFilter ?? true;

  if (minPeriod <= 0 || maxPeriod <= minPeriod) {
    throw new Error(`Invalid period bounds: min=${minPeriod}, max=${maxPeriod}`);
  }
  if (maxAngle <= minAngle) {
    throw new Error(`Invalid angle bounds: min=${minAngle}, max=${maxAngle}`);
  }

  const { width, height, bitDepth, data } = source;
  const totalCells = width * height;
  const maxVal = bitDepth === 16 ? 65535.0 : 255.0;
  const alphaThresh = bitDepth === 16 ? 32768 : 128;

  let periodNm: Uint32Array = new Uint32Array(totalCells);
  let angleDeg: Float64Array = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);

  const periodRange = maxPeriod - minPeriod;
  const angleRange = maxAngle - minAngle;

  let srcIdx = 0;
  for (let i = 0; i < totalCells; i++) {
    const r = data[srcIdx];
    const g = data[srcIdx + 1];
    // b = data[srcIdx + 2] (ignored)
    const a = data[srcIdx + 3];
    srcIdx += 4;

    if (a >= alphaThresh) {
      active[i] = 1;
      const rawPeriod = minPeriod + (r / maxVal) * periodRange;
      periodNm[i] = Math.round(rawPeriod);
      const rawAngle = minAngle + (g / maxVal) * angleRange;
      angleDeg[i] = rawAngle;
    } else {
      active[i] = 0;
      periodNm[i] = 0;
      angleDeg[i] = 0.0;
    }
  }

  if (applyFilter) {
    const filtered = applyMaskedBilateralFilter(
      width,
      height,
      periodNm,
      angleDeg,
      active,
      options?.filterDiameter ?? 3,
      options?.filterSigmaColorPeriod ?? 50.0,
      options?.filterSigmaColorAngle ?? 10.0,
      options?.filterSigmaSpace ?? 100.0,
      true,
      true
    );
    periodNm = filtered.periodNm;
    angleDeg = filtered.angleDeg;
  }

  const roundPeriod50Nm = options?.roundPeriod50Nm ?? false;
  if (roundPeriod50Nm) {
    for (let i = 0; i < totalCells; i++) {
      if (active[i]) {
        periodNm[i] = roundHalfAwayFromZero(periodNm[i] / 50.0) * 50;
      }
    }
  }

  const roundIntegerAngles = options?.roundIntegerAngles ?? false;
  if (roundIntegerAngles) {
    for (let i = 0; i < totalCells; i++) {
      if (active[i]) {
        angleDeg[i] = roundHalfAwayFromZero(angleDeg[i]);
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
    sourceIdentity: `rgba-continuous:${source.filename}`,
  };
}
