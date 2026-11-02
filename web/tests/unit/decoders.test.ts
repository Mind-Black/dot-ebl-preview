import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { decodeHls } from '@/lib/decoders/hls';
import { decodeRgb16Fixed } from '@/lib/decoders/rgbFixed';
import { decodeRgb8Indexed } from '@/lib/decoders/rgbIndexed';
import { decodeUnityHsv } from '@/lib/decoders/unity';
import { parseNpz } from '@/lib/io/npzParser';
import { parsePng } from '@/lib/io/pngParser';

const FIXTURES_DIR = fileURLToPath(new URL('../fixtures', import.meta.url));

describe('PNG Parser and Image Decoders', () => {
  it('parses 8-bit RGB PNG preserving exact channel samples', () => {
    const bytes = readFileSync(resolve(FIXTURES_DIR, 'rgb8_test.png'));
    const source = parsePng(bytes, 'rgb8_test.png');

    expect(source.width).toBe(4);
    expect(source.height).toBe(4);
    expect(source.bitDepth).toBe(8);
    expect(source.channels).toBe(3);
    expect(source.data.length).toBe(4 * 4 * 3);
  });

  it('parses 16-bit RGB PNG preserving exact uint16 channel samples without downconversion', () => {
    const bytes = readFileSync(resolve(FIXTURES_DIR, 'rgb16_test.png'));
    const source = parsePng(bytes, 'rgb16_test.png');

    expect(source.width).toBe(4);
    expect(source.height).toBe(4);
    expect(source.bitDepth).toBe(16);
    expect(source.channels).toBe(3);
    expect(source.data).toBeInstanceOf(Uint16Array);
    expect(source.data.length).toBe(4 * 4 * 3);
  });

  it('decodes RGB8 indexed profile exactly matching Python reference fixtures', () => {
    const bytes = readFileSync(resolve(FIXTURES_DIR, 'rgb8_test.png'));
    const expected = JSON.parse(readFileSync(resolve(FIXTURES_DIR, 'rgb8_expected.json'), 'utf-8'));
    const source = parsePng(bytes, 'rgb8_test.png');

    const design = decodeRgb8Indexed(source);

    expect(design.width).toBe(expected.shape[1]);
    expect(design.height).toBe(expected.shape[0]);
    expect(design.pitchNm).toBe(expected.pitch_nm);

    const expPeriods = expected.period_nm.flat();
    const expAngles = expected.angle_deg.flat();
    const expActive = expected.active.flat();

    for (let i = 0; i < design.width * design.height; i++) {
      expect(design.active[i]).toBe(expActive[i]);
      expect(design.periodNm[i]).toBe(expPeriods[i]);
      expect(design.angleDeg[i]).toBeCloseTo(expAngles[i], 5);
    }
  });

  it('treats any B >= 5 as active and B < 5 as inactive in RGB8 indexed profile', () => {
    const data = new Uint8Array([
      0, 90, 128, // B = 128 -> active
      0, 90, 4, // B = 4 -> discarded
      0, 90, 5, // B = 5 -> active
    ]);
    const source = {
      width: 3,
      height: 1,
      channels: 3,
      bitDepth: 8 as const,
      data,
      filename: 'b_threshold.png',
    };

    const design = decodeRgb8Indexed(source);
    expect(Array.from(design.active)).toEqual([1, 0, 1]);
  });

  it('decodes RGB16 fixed profile exactly matching Python reference fixtures', () => {
    const bytes = readFileSync(resolve(FIXTURES_DIR, 'rgb16_test.png'));
    const expected = JSON.parse(readFileSync(resolve(FIXTURES_DIR, 'rgb16_expected.json'), 'utf-8'));
    const source = parsePng(bytes, 'rgb16_test.png');

    const design = decodeRgb16Fixed(source);

    expect(design.width).toBe(expected.shape[1]);
    expect(design.height).toBe(expected.shape[0]);
    expect(design.pitchNm).toBe(expected.pitch_nm);

    const expPeriods = expected.period_nm.flat();
    const expAngles = expected.angle_deg.flat();
    const expActive = expected.active.flat();

    for (let i = 0; i < design.width * design.height; i++) {
      expect(design.active[i]).toBe(expActive[i]);
      const expectedPeriod = expActive[i] ? Math.max(400, Math.min(1600, expPeriods[i])) : 0;
      expect(design.periodNm[i]).toBe(expectedPeriod);
      expect(design.angleDeg[i]).toBeCloseTo(expAngles[i], 2);
    }
  });

  it('applies the B >= 5 activity threshold and clamps periods to [400, 1600] nm in RGB16 fixed profile', () => {
    // Any B >= 5 is active; B < 5 is discarded.
    const dataB = new Uint16Array([1000, 32768, 255, 1000, 32768, 4]);
    const sourceB = {
      width: 2,
      height: 1,
      channels: 3,
      bitDepth: 16 as const,
      data: dataB,
      filename: 'b_threshold.png',
    };
    expect(Array.from(decodeRgb16Fixed(sourceB).active)).toEqual([1, 0]);

    // Test period < 400 nm clamped to 400 nm and > 1600 nm clamped to 1600 nm
    const dataClamped = new Uint16Array([50, 32768, 65535, 2500, 32768, 65535]);
    const sourceClamped = {
      width: 2,
      height: 1,
      channels: 3,
      bitDepth: 16 as const,
      data: dataClamped,
      filename: 'clamped_period.png',
    };
    const designClamped = decodeRgb16Fixed(sourceClamped);
    expect(designClamped.periodNm[0]).toBe(400);
    expect(designClamped.periodNm[1]).toBe(1600);
  });

  it('decodes HLS image with radial gradient matching Python reference fixtures', () => {
    const bytes = readFileSync(resolve(FIXTURES_DIR, 'hls_test.png'));
    const expected = JSON.parse(readFileSync(resolve(FIXTURES_DIR, 'hls_expected.json'), 'utf-8'));
    const source = parsePng(bytes, 'hls_test.png');

    const design = decodeHls(source, 'holtida-ebl', 20000, true);

    expect(design.width).toBe(expected.shape[1]);
    expect(design.height).toBe(expected.shape[0]);

    const expPeriods = expected.period_nm.flat();
    const expAngles = expected.angle_deg.flat();
    const expActive = expected.active.flat();

    for (let i = 0; i < design.width * design.height; i++) {
      expect(design.active[i]).toBe(expActive[i]);
      expect(design.periodNm[i]).toBe(expPeriods[i]);
      expect(design.angleDeg[i]).toBeCloseTo(expAngles[i], 1);
    }
  });

  it('decodes Unity HSV image matching Python reference fixtures', () => {
    const bytes = readFileSync(resolve(FIXTURES_DIR, 'unity_test.png'));
    const expected = JSON.parse(readFileSync(resolve(FIXTURES_DIR, 'unity_expected.json'), 'utf-8'));
    const source = parsePng(bytes, 'unity_test.png');

    const design = decodeUnityHsv(source, 60000);

    expect(design.width).toBe(expected.shape[1]);
    expect(design.height).toBe(expected.shape[0]);

    const expPeriods = expected.period_nm.flat();
    const expAngles = expected.angle_deg.flat();
    const expActive = expected.active.flat();

    for (let i = 0; i < design.width * design.height; i++) {
      expect(design.active[i]).toBe(expActive[i]);
      expect(design.periodNm[i]).toBe(expPeriods[i]);
      expect(design.angleDeg[i]).toBeCloseTo(expAngles[i], 1);
    }
  });

  it('parses Python .npz design archives directly without Python backend', () => {
    const bytes = readFileSync(resolve(FIXTURES_DIR, 'design.npz'));
    const expected = JSON.parse(readFileSync(resolve(FIXTURES_DIR, 'rgb16_expected.json'), 'utf-8'));

    const design = parseNpz(bytes, 'design.npz');

    expect(design.width).toBe(expected.shape[1]);
    expect(design.height).toBe(expected.shape[0]);
    expect(design.pitchNm).toBe(expected.pitch_nm);

    const expPeriods = expected.period_nm.flat();
    const expAngles = expected.angle_deg.flat();
    const expActive = expected.active.flat();

    for (let i = 0; i < design.width * design.height; i++) {
      expect(design.active[i]).toBe(expActive[i]);
      expect(design.periodNm[i]).toBe(expPeriods[i]);
      expect(design.angleDeg[i]).toBeCloseTo(expAngles[i], 2);
    }
  });
});
