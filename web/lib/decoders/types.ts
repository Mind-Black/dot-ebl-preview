/**
 * Canonical Design data model matching dot-ebl-preview physical contract.
 */

export const MIN_PERIOD_NM = 400;
export const MAX_PERIOD_NM = 1600;

export type InterpretationFormat =
  | 'RGBA continuous'
  | 'RGB8 indexed'
  | 'RGB16 fixed'
  | 'Holtida legacy HLS'
  | 'Learning Shaders HLS'
  | 'Unity HSV'
  | 'NPZ design';

export interface DesignModel {
  width: number;
  height: number;
  pitchNm: number; // Positive safe integer nanometres
  periodNm: Uint32Array; // Row-major, width * height
  angleDeg: Float64Array; // Preserve Python CPU precision
  active: Uint8Array; // Exactly 0 or 1
  appearanceRgb?: Float32Array; // RGB, 3 * width * height, [0, 1]
  fallbackIntensity?: Float32Array; // Scalar per cell, [0, 1]
  layer?: number;
  dose?: number;
  artifactMetadata?: Record<string, unknown>;
  regionMasks?: Record<string, Uint8Array>;
  sourceIdentity: string;
}

export interface RawImageSource {
  width: number;
  height: number;
  channels: number; // 3 for RGB, 4 for RGBA
  bitDepth: 8 | 16;
  data: Uint8Array | Uint16Array; // channel-interleaved row-major samples
  formatHint?: string;
  filename: string;
}

export interface ParameterStats {
  totalCells: number;
  activeCells: number;
  fillFactor: number;
  widthMm: number;
  heightMm: number;
  uniquePeriods: { periodNm: number; count: number }[];
  uniqueAngles: { angleDeg: number; count: number }[];
  minPeriodNm: number;
  maxPeriodNm: number;
  minAngleDeg: number;
  maxAngleDeg: number;
}
