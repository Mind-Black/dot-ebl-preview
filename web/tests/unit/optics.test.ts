import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  cellCenterMm,
  directionFromPosition,
  positionFromDirection,
} from '@/lib/optics/coordinates';
import {
  REFL_NI_77,
  S2XYZ_77,
  SPECTRAL_BALANCED,
  SPECTRAL_HIGH,
  SPECTRAL_PERFORMANCE,
  STD_ILLUM_D65_77,
} from '@/lib/optics/tables';
import {
  createConcentricTestPattern,
  createEblGlyph,
  createOrthogonalCross,
  createSpectralFan,
} from '@/lib/presets/sampleDesigns';

const FIXTURES_DIR = fileURLToPath(new URL('../fixtures', import.meta.url));

describe('Optical Tables and Coordinates', () => {
  it('matches Python CIE 1931, D65, and Nickel spectral tables across all 77 bands', () => {
    const spectral = JSON.parse(readFileSync(resolve(FIXTURES_DIR, 'spectral_tables.json'), 'utf-8'));

    // S2XYZ (380 to 760 nm)
    for (let i = 0; i < 77; i++) {
      expect(S2XYZ_77[i][0]).toBeCloseTo(spectral.s2xyz[0][i], 5);
      expect(S2XYZ_77[i][1]).toBeCloseTo(spectral.s2xyz[1][i], 5);
      expect(S2XYZ_77[i][2]).toBeCloseTo(spectral.s2xyz[2][i], 5);

      expect(STD_ILLUM_D65_77[i]).toBeCloseTo(spectral.stdIllum[i], 3);
      expect(REFL_NI_77[i]).toBeCloseTo(spectral.reflNi[i], 5);
    }

    // High quality config: 77 bands
    expect(SPECTRAL_HIGH.numBands).toBe(77);
    expect(SPECTRAL_HIGH.wavelengthStepNm).toBe(5.0);

    for (let i = 0; i < 77; i++) {
      const px = SPECTRAL_HIGH.premultipliedXyz[i * 4 + 0];
      const py = SPECTRAL_HIGH.premultipliedXyz[i * 4 + 1];
      const pz = SPECTRAL_HIGH.premultipliedXyz[i * 4 + 2];

      expect(px).toBeCloseTo(spectral.premultiplied_XYZ[i][0], 4);
      expect(py).toBeCloseTo(spectral.premultiplied_XYZ[i][1], 4);
      expect(pz).toBeCloseTo(spectral.premultiplied_XYZ[i][2], 4);
    }

    // Derived white point & lightY
    const pySum = spectral.premultiplied_XYZ.reduce((acc: number, row: number[]) => acc + row[1], 0);
    expect(SPECTRAL_HIGH.lightY).toBeCloseTo(pySum, 3);
  });

  it('provides verified downsampled tables for Balanced (39) and Performance (19) quality', () => {
    expect(SPECTRAL_BALANCED.numBands).toBe(39);
    expect(SPECTRAL_BALANCED.wavelengthStepNm).toBe(10.0);
    expect(SPECTRAL_BALANCED.wavelengthsNm[0]).toBe(380.0);
    expect(SPECTRAL_BALANCED.wavelengthsNm[38]).toBe(760.0);

    expect(SPECTRAL_PERFORMANCE.numBands).toBe(20);
    expect(SPECTRAL_PERFORMANCE.wavelengthStepNm).toBe(20.0);
    expect(SPECTRAL_PERFORMANCE.wavelengthsNm[0]).toBe(380.0);
    expect(SPECTRAL_PERFORMANCE.wavelengthsNm[19]).toBe(760.0);
  });

  it('transforms spherical and Cartesian coordinates symmetrically', () => {
    const testCases = [
      { az: 90, el: 35, dist: 400 },
      { az: 0, el: 45, dist: 300 },
      { az: 180, el: 60, dist: 250 },
      { az: 270, el: 15, dist: 500 },
    ];

    for (const tc of testCases) {
      const pos = positionFromDirection(tc.az, tc.el, tc.dist);
      const roundTrip = directionFromPosition(pos);

      // Normalize azimuth to [0, 360)
      let normAz = (roundTrip.azimuthDeg + 360) % 360;
      if (Math.abs(normAz - 360) < 1e-4) normAz = 0;

      expect(normAz).toBeCloseTo(tc.az, 3);
      expect(roundTrip.elevationDeg).toBeCloseTo(tc.el, 3);
      expect(roundTrip.distanceMm).toBeCloseTo(tc.dist, 3);
    }
  });

  it('computes exact cell centers in millimeters matching fabrication grid layout', () => {
    const center = cellCenterMm(0, 0, 10, 10, 20000);
    // col=0: (0 + 0.5 - 5) * 0.02 = -4.5 * 0.02 = -0.09 mm
    // row=0: -(0 + 0.5 - 5) * 0.02 = +4.5 * 0.02 = +0.09 mm
    expect(center.x).toBeCloseTo(-0.09, 6);
    expect(center.y).toBeCloseTo(0.09, 6);
    expect(center.z).toBe(0.0);
  });

  it('generates valid procedural sample designs with physical parameter constraints', () => {
    const presets = [
      createConcentricTestPattern(64),
      createOrthogonalCross(64),
      createSpectralFan(64),
      createEblGlyph(64),
    ];

    for (const design of presets) {
      expect(design.width).toBe(64);
      expect(design.height).toBe(64);
      expect(design.pitchNm).toBeGreaterThan(0);

      let activeCount = 0;
      for (let i = 0; i < 64 * 64; i++) {
        if (design.active[i]) {
          activeCount++;
          expect(design.periodNm[i]).toBeGreaterThan(0);
          expect(Number.isFinite(design.angleDeg[i])).toBe(true);
        }
      }
      expect(activeCount).toBeGreaterThan(0);
    }
  });
});
