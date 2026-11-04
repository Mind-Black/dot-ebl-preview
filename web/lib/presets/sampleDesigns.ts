/**
 * Procedural physical test designs (bypass image decoding directly into physical parameters).
 */

import type { DesignModel } from '../decoders/types';

export interface SamplePreset {
  id: string;
  title: string;
  description: string;
  generator: () => DesignModel;
}

export function createConcentricTestPattern(size = 128): DesignModel {
  const width = size;
  const height = size;
  const pitchNm = 20000;
  const totalCells = width * height;

  const periodNm = new Uint32Array(totalCells);
  const angleDeg = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);

  const centerX = width / 2.0;
  const centerY = height / 2.0;
  const maxRadius = Math.min(centerX, centerY) - 2;

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const idx = r * width + c;
      const dx = c + 0.5 - centerX;
      const dy = r + 0.5 - centerY;
      const dist = Math.hypot(dx, dy);

      if (dist <= maxRadius) {
        active[idx] = 1;
        // Ring bands every 8 pixels
        const ringIdx = Math.floor(dist / 8);
        periodNm[idx] = 900 + (ringIdx % 4) * 100; // 900, 1000, 1100, 1200 nm

        // Tangential orientation (perpendicular to radius vector)
        const radAngle = Math.atan2(dy, dx);
        let deg = (radAngle * 180.0) / Math.PI + 90.0;
        while (deg > 90.0) deg -= 180.0;
        while (deg < -90.0) deg += 180.0;
        angleDeg[idx] = deg;

        // Asymmetry notch in top-left quadrant (row < height/4 and col < width/4) to detect flips
        if (r < height / 4 && c < width / 4) {
          angleDeg[idx] = 0.0;
          periodNm[idx] = 1300;
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
    sourceIdentity: 'preset:concentric-test-pattern',
  };
}

export function createOrthogonalCross(size = 128): DesignModel {
  const width = size;
  const height = size;
  const pitchNm = 20000;
  const totalCells = width * height;

  const periodNm = new Uint32Array(totalCells);
  const angleDeg = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);

  const halfW = width / 2;
  const halfH = height / 2;
  const barThickness = Math.max(8, Math.floor(size / 6));

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const idx = r * width + c;
      const inHorizBar = Math.abs(r - halfH) <= barThickness / 2;
      const inVertBar = Math.abs(c - halfW) <= barThickness / 2;

      if (inHorizBar || inVertBar) {
        active[idx] = 1;
        if (inHorizBar && !inVertBar) {
          periodNm[idx] = 1000;
          angleDeg[idx] = 0.0; // Horizontal lines
        } else if (inVertBar && !inHorizBar) {
          periodNm[idx] = 1150;
          angleDeg[idx] = 90.0; // Vertical lines
        } else {
          // Center intersection: 45° diagonal with asymmetry
          periodNm[idx] = 1100;
          angleDeg[idx] = 45.0;
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
    sourceIdentity: 'preset:orthogonal-cross',
  };
}

export function createSpectralFan(size = 128): DesignModel {
  const width = size;
  const height = size;
  const pitchNm = 20000;
  const totalCells = width * height;

  const periodNm = new Uint32Array(totalCells);
  const angleDeg = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const idx = r * width + c;
      // Border margin
      if (r >= 4 && r < height - 4 && c >= 4 && c < width - 4) {
        active[idx] = 1;
        // Period sweeps smoothly from 900 nm to 1200 nm along Y (rows)
        const rowFrac = (r - 4) / (height - 8);
        periodNm[idx] = Math.round(900 + rowFrac * 300);

        // Angle sweeps from -90° to +90° along X (cols)
        const colFrac = (c - 4) / (width - 8);
        angleDeg[idx] = -90.0 + colFrac * 180.0;
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
    sourceIdentity: 'preset:spectral-fan',
  };
}

export function createEblGlyph(size = 128): DesignModel {
  const width = size;
  const height = size;
  const pitchNm = 20000;
  const totalCells = width * height;

  const periodNm = new Uint32Array(totalCells);
  const angleDeg = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);

  // Draw 'EBL' glyph emblem
  // Tile dimensions
  const scale = size / 64;
  const inLetterE = (r: number, c: number) => {
    const rx = c / scale - 8;
    const ry = r / scale - 16;
    if (rx < 0 || rx > 14 || ry < 0 || ry > 32) return false;
    if (rx <= 4) return true; // spine
    if (ry <= 4 || ry >= 28) return true; // top / bottom
    if (ry >= 14 && ry <= 18 && rx <= 11) return true; // middle
    return false;
  };

  const inLetterB = (r: number, c: number) => {
    const rx = c / scale - 26;
    const ry = r / scale - 16;
    if (rx < 0 || rx > 14 || ry < 0 || ry > 32) return false;
    if (rx <= 4) return true; // spine
    if (ry <= 4 || ry >= 28) return true; // top / bottom
    if (ry >= 14 && ry <= 18) return true; // middle
    if (rx >= 10 && (ry <= 16 || ry >= 16)) return true; // right loops
    return false;
  };

  const inLetterL = (r: number, c: number) => {
    const rx = c / scale - 44;
    const ry = r / scale - 16;
    if (rx < 0 || rx > 14 || ry < 0 || ry > 32) return false;
    if (rx <= 4) return true; // spine
    if (ry >= 28) return true; // bottom foot
    return false;
  };

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const idx = r * width + c;
      if (inLetterE(r, c)) {
        active[idx] = 1;
        periodNm[idx] = 950;
        angleDeg[idx] = -30.0;
      } else if (inLetterB(r, c)) {
        active[idx] = 1;
        periodNm[idx] = 1050;
        angleDeg[idx] = 15.0;
      } else if (inLetterL(r, c)) {
        active[idx] = 1;
        periodNm[idx] = 1180;
        angleDeg[idx] = 60.0;
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
    sourceIdentity: 'preset:ebl-glyph',
  };
}

/**
 * Default 256x256 showcase hologram illustrating micro-grating dot-matrix capabilities:
 * - Zone 1: Precision Vernier Bezel Ring (tangential tracking beacon)
 * - Zone 2: Kinetic Logarithmic Spiral Starburst (expanding wave motion & period chirp)
 * - Zone 3: Concentric Spectral Rainbow Dispersion Band (6 visible spectrum steps)
 * - Zone 4: Dual-Channel Orthogonal Switching Ring (angular multiplexing 0° vs 90°)
 * - Zone 5: 8-Facet Prismatic Crystal Core & focal spark dot
 */
export function createShowcaseHologram(size = 256): DesignModel {
  const width = size;
  const height = size;
  const pitchNm = 20000;
  const totalCells = width * height;

  const periodNm = new Uint32Array(totalCells);
  const angleDeg = new Float64Array(totalCells);
  const active = new Uint8Array(totalCells);

  const cx = width / 2.0;
  const cy = height / 2.0;
  const maxR = size / 2.0 - 4; // 124 for size 256

  function normAngle(deg: number): number {
    let a = deg;
    while (a > 90.0) a -= 180.0;
    while (a < -90.0) a += 180.0;
    return a;
  }

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      const idx = r * width + c;
      const dx = c + 0.5 - cx;
      const dy = r + 0.5 - cy;
      const dist = Math.hypot(dx, dy);

      if (dist > maxR) {
        // Zone 0: Inactive corner margin
        active[idx] = 0;
        continue;
      }

      const rad = Math.atan2(dy, dx);
      const deg = (rad * 180.0) / Math.PI;

      // Zone 1: Precision Vernier Bezel Ring (114 <= dist <= 124)
      if (dist >= 114) {
        const tickModulo = Math.abs((((deg % 15) + 15) % 15) - 7.5);
        const isTick = tickModulo > 6.2;

        active[idx] = 1;
        if (isTick) {
          // Radial tick marks
          periodNm[idx] = 1250;
          angleDeg[idx] = normAngle(deg);
        } else {
          // Tangential bezel tracking orbiting light
          periodNm[idx] = 1020;
          angleDeg[idx] = normAngle(deg + 90.0);
        }
      }
      // Zone 2: Kinetic Logarithmic Spiral Starburst (74 <= dist < 114)
      else if (dist >= 74) {
        // 16 logarithmic spiral rays
        const armIndex = (16.0 / (2.0 * Math.PI)) * (rad - 1.8 * Math.log(dist / 74.0));
        const armFrac = armIndex - Math.floor(armIndex);

        if (armFrac < 0.65) {
          active[idx] = 1;
          // Continuous period chirp from 920 nm to 1280 nm
          const chirpFrac = (dist - 74.0) / (114.0 - 74.0);
          periodNm[idx] = Math.round(920.0 + chirpFrac * 360.0);

          // Coupled spiral wave angle
          const spiralWaveAngle = deg + 45.0 * Math.sin(armIndex * 2.0 * Math.PI) + 30.0 * Math.log(dist / 74.0);
          angleDeg[idx] = normAngle(spiralWaveAngle);
        } else {
          active[idx] = 0;
        }
      }
      // Zone 3: Concentric Spectral Rainbow Dispersion Band (52 <= dist < 74)
      else if (dist >= 52) {
        active[idx] = 1;
        // 6 calibrated visible spectrum steps
        if (dist >= 70) {
          periodNm[idx] = 1380; // Ruby Red
        } else if (dist >= 66) {
          periodNm[idx] = 1260; // Vibrant Orange
        } else if (dist >= 62) {
          periodNm[idx] = 1150; // Luminous Yellow-Green
        } else if (dist >= 58) {
          periodNm[idx] = 1050; // Emerald Green
        } else if (dist >= 55) {
          periodNm[idx] = 950;  // Peacock Cyan
        } else {
          periodNm[idx] = 860;  // Sapphire Blue/Violet
        }
        // Radial grating lines creating rotating rainbow dispersion cross
        angleDeg[idx] = normAngle(deg);
      }
      // Zone 4: Dual-Channel Orthogonal Switching Ring (34 <= dist < 52)
      else if (dist >= 34) {
        active[idx] = 1;
        // 12 alternating 30° sectors
        const sector = Math.floor(((deg + 180.0) % 360.0) / 30.0);
        if (sector % 2 === 0) {
          // Channel A: Horizontal gratings (active on horizontal illumination)
          periodNm[idx] = 1000;
          angleDeg[idx] = 0.0;
        } else {
          // Channel B: Vertical gratings (active on vertical illumination)
          periodNm[idx] = 1180;
          angleDeg[idx] = 90.0;
        }
      }
      // Zone 5: Prismatic Crystal Core (dist < 34)
      else {
        active[idx] = 1;
        if (dist <= 6) {
          // Central focal spark dot
          periodNm[idx] = 850;
          angleDeg[idx] = 45.0;
        } else {
          // 8-facet prismatic star
          const facet = Math.floor(((deg + 180.0) % 360.0) / 45.0);
          const facetAngle = -180.0 + facet * 45.0 + 22.5;
          periodNm[idx] = 1080;
          angleDeg[idx] = normAngle(facetAngle + 90.0);
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
    sourceIdentity: 'preset:showcase-hologram-256',
  };
}

export const SAMPLE_PRESETS: SamplePreset[] = [
  {
    id: 'concentric-test-pattern',
    title: 'Concentric Test Pattern',
    description: 'Circular rings with tangential orientations and asymmetric quadrant marker.',
    generator: () => createConcentricTestPattern(128),
  },
  {
    id: 'orthogonal-cross',
    title: 'Orthogonal Cross',
    description: 'Horizontal and vertical grating domains (0° / 90°) with 45° intersection.',
    generator: () => createOrthogonalCross(128),
  },
  {
    id: 'spectral-fan',
    title: 'Spectral Fan Sweep',
    description: 'Continuous parameter gradient across orientation (-90° to +90°) and period (900–1200 nm).',
    generator: () => createSpectralFan(128),
  },
  {
    id: 'ebl-glyph',
    title: 'EBL Glyph Emblem',
    description: 'Distinct alphanumeric tiles with known orientation and period combinations.',
    generator: () => createEblGlyph(128),
  },
];
