import { describe, it, expect } from 'vitest';
import { createShowcaseHologram } from '../../lib/presets/sampleDesigns';

describe('Showcase Hologram Generator (256x256)', () => {
  it('generates exact 256x256 dimensions with 20um pitch', () => {
    const design = createShowcaseHologram(256);
    expect(design.width).toBe(256);
    expect(design.height).toBe(256);
    expect(design.pitchNm).toBe(20000);
    expect(design.periodNm).toHaveLength(256 * 256);
    expect(design.angleDeg).toHaveLength(256 * 256);
    expect(design.active).toHaveLength(256 * 256);
    expect(design.sourceIdentity).toBe('preset:showcase-hologram-256');
  });

  it('bounds all active grating periods to physical visible spectrum (800 - 1450 nm)', () => {
    const design = createShowcaseHologram(256);
    let activeCount = 0;
    for (let i = 0; i < design.active.length; i++) {
      if (design.active[i]) {
        activeCount++;
        const period = design.periodNm[i];
        expect(period).toBeGreaterThanOrEqual(800);
        expect(period).toBeLessThanOrEqual(1450);
      }
    }
    // Disc of radius ~124 on a 256x256 array with spiral spacing
    expect(activeCount).toBeGreaterThan(25000);
    expect(activeCount).toBeLessThan(50000);
  });

  it('strictly bounds all rotation angles to [-90, +90] degrees', () => {
    const design = createShowcaseHologram(256);
    for (let i = 0; i < design.active.length; i++) {
      if (design.active[i]) {
        const deg = design.angleDeg[i];
        expect(deg).toBeGreaterThanOrEqual(-90.0);
        expect(deg).toBeLessThanOrEqual(90.0);
      }
    }
  });

  it('frames with inactive substrate at the corner margins', () => {
    const design = createShowcaseHologram(256);
    const corners = [
      0, // top-left (0, 0)
      255, // top-right (0, 255)
      255 * 256, // bottom-left (255, 0)
      255 * 256 + 255, // bottom-right (255, 255)
    ];
    for (const idx of corners) {
      expect(design.active[idx]).toBe(0);
    }
    // Center pixel is active
    const centerIdx = 128 * 256 + 128;
    expect(design.active[centerIdx]).toBe(1);
  });

  it('contains dual-channel orthogonal orientations and multi-spectral dispersion bands', () => {
    const design = createShowcaseHologram(256);
    const periods = new Set<number>();
    const angles = new Set<number>();

    for (let i = 0; i < design.active.length; i++) {
      if (design.active[i]) {
        periods.add(design.periodNm[i]);
        angles.add(Math.round(design.angleDeg[i] * 10) / 10);
      }
    }

    // Must exhibit multiple discrete period bands across visible spectrum
    expect(periods.size).toBeGreaterThan(20);
    expect(periods.has(850)).toBe(true);
    expect(periods.has(1000)).toBe(true);
    expect(periods.has(1180)).toBe(true);
    expect(periods.has(1380)).toBe(true);

    // Must exhibit rich angular diversity
    expect(angles.size).toBeGreaterThan(50);
  });

  it('produces deterministic output across repeated invocations', () => {
    const d1 = createShowcaseHologram(256);
    const d2 = createShowcaseHologram(256);
    expect(d1.active).toEqual(d2.active);
    expect(d1.periodNm).toEqual(d2.periodNm);
    expect(d1.angleDeg).toEqual(d2.angleDeg);
  });
});
