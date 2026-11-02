import { zlibSync } from 'fflate';
import { describe, expect, it } from 'vitest';
import {
  applyMaskedBilateralFilter,
  decodeRgbaContinuous,
  liftToNearestBranch,
  roundHalfAwayFromZero,
} from '@/lib/decoders/rgbaContinuous';
import { decodeDesign } from '@/lib/decoders';
import { parsePng } from '@/lib/io/pngParser';
import { designStore } from '@/lib/store/designStore';
import type { RawImageSource } from '@/lib/decoders/types';

function createCrc32(buf: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc ^= buf[i];
    for (let j = 0; j < 8; j++) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function buildPng(width: number, height: number, bitDepth: 8 | 16, colorType: 6, rawPixelData: Uint8Array): Uint8Array {
  // rawPixelData has 1 filter byte (0) per row followed by row samples
  const compressed = zlibSync(rawPixelData);

  const totalLength = 8 + 25 + (12 + compressed.length) + 12;
  const png = new Uint8Array(totalLength);
  const view = new DataView(png.buffer);

  // Signature
  png.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0);

  // IHDR chunk
  let offset = 8;
  view.setUint32(offset, 13, false);
  offset += 4;
  png.set([0x49, 0x48, 0x44, 0x52], offset); // "IHDR"
  offset += 4;
  view.setUint32(offset, width, false);
  view.setUint32(offset + 4, height, false);
  png[offset + 8] = bitDepth;
  png[offset + 9] = colorType;
  png[offset + 10] = 0; // compression
  png[offset + 11] = 0; // filter
  png[offset + 12] = 0; // interlace
  const ihdrCrc = createCrc32(png.subarray(offset - 4, offset + 13));
  offset += 13;
  view.setUint32(offset, ihdrCrc, false);
  offset += 4;

  // IDAT chunk
  view.setUint32(offset, compressed.length, false);
  offset += 4;
  png.set([0x49, 0x44, 0x41, 0x54], offset); // "IDAT"
  offset += 4;
  png.set(compressed, offset);
  const idatCrc = createCrc32(png.subarray(offset - 4, offset + compressed.length));
  offset += compressed.length;
  view.setUint32(offset, idatCrc, false);
  offset += 4;

  // IEND chunk
  view.setUint32(offset, 0, false);
  offset += 4;
  png.set([0x49, 0x45, 0x4e, 0x44], offset); // "IEND"
  offset += 4;
  const iendCrc = createCrc32(png.subarray(offset - 4, offset));
  view.setUint32(offset, iendCrc, false);

  return png;
}

describe('RGBA Continuous Decoder and PNG Parser', () => {
  it('parses 8-bit RGBA PNG (color type 6) correctly', () => {
    // 2x1 image, 4 channels per pixel
    const rawScanlines = new Uint8Array([
      0, // filter none
      100, 50, 0, 255, // pixel 0
      200, 150, 0, 255, // pixel 1
    ]);
    const pngBytes = buildPng(2, 1, 8, 6, rawScanlines);
    const source = parsePng(pngBytes, 'test8.png');

    expect(source.width).toBe(2);
    expect(source.height).toBe(1);
    expect(source.channels).toBe(4);
    expect(source.bitDepth).toBe(8);
    expect(Array.from(source.data)).toEqual([100, 50, 0, 255, 200, 150, 0, 255]);
  });

  it('parses 16-bit RGBA PNG (color type 6) correctly', () => {
    // 1x1 image, 4 channels uint16 (8 bytes)
    const rawScanlines = new Uint8Array([
      0, // filter none
      0x10, 0x00, // R = 4096
      0x20, 0x00, // G = 8192
      0x00, 0x00, // B = 0
      0x80, 0x00, // A = 32768
    ]);
    const pngBytes = buildPng(1, 1, 16, 6, rawScanlines);
    const source = parsePng(pngBytes, 'test16.png');

    expect(source.width).toBe(1);
    expect(source.height).toBe(1);
    expect(source.channels).toBe(4);
    expect(source.bitDepth).toBe(16);
    expect(source.data).toBeInstanceOf(Uint16Array);
    expect(Array.from(source.data)).toEqual([4096, 8192, 0, 32768]);
  });

  it('decodes 8-bit RGBA linear period and angle accurately', () => {
    // 3 pixels: R=0 (min period), R=255 (max period), R=128 (mid period)
    // G=0 (min angle -90), G=255 (max angle +90), G=128 (mid angle ~0.35)
    // A=255 (active), A=128 (active threshold), A=127 (inactive)
    const data = new Uint8Array([
      0, 0, 99, 255, // pixel 0: R=0 -> 400nm, G=0 -> -90 deg, B=99 ignored, A=255 active
      255, 255, 0, 128, // pixel 1: R=255 -> 1600nm, G=255 -> +90 deg, A=128 active
      128, 128, 0, 127, // pixel 2: A=127 -> inactive, period=0, angle=0
    ]);
    const source: RawImageSource = {
      width: 3,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'linear_8bit.png',
    };

    const design = decodeRgbaContinuous(source, { applyFilter: false });

    expect(design.active[0]).toBe(1);
    expect(design.periodNm[0]).toBe(400);
    expect(design.angleDeg[0]).toBeCloseTo(-90.0, 4);

    expect(design.active[1]).toBe(1);
    expect(design.periodNm[1]).toBe(1600);
    expect(design.angleDeg[1]).toBeCloseTo(90.0, 4);

    // Inactive cell outputs 0 period and 0 angle
    expect(design.active[2]).toBe(0);
    expect(design.periodNm[2]).toBe(0);
    expect(design.angleDeg[2]).toBe(0.0);

    const viaDispatcher = decodeDesign(source, 'RGBA continuous');
    expect(viaDispatcher.sourceIdentity).toContain('rgba-continuous:linear_8bit.png');
    expect(viaDispatcher.periodNm[1]).toBe(1600);
  });

  it('decodes 16-bit RGBA with precision and threshold at 32768', () => {
    const data = new Uint16Array([
      0, 0, 0, 65535, // pixel 0: active, 400nm, -90 deg
      65535, 65535, 0, 32768, // pixel 1: active, 1600nm, +90 deg
      32768, 32768, 0, 32767, // pixel 2: inactive (<32768), period=0, angle=0
    ]);
    const source: RawImageSource = {
      width: 3,
      height: 1,
      channels: 4,
      bitDepth: 16,
      data,
      filename: 'linear_16bit.png',
    };

    const design = decodeRgbaContinuous(source, { applyFilter: false });

    expect(design.active[0]).toBe(1);
    expect(design.periodNm[0]).toBe(400);
    expect(design.angleDeg[0]).toBeCloseTo(-90.0, 5);

    expect(design.active[1]).toBe(1);
    expect(design.periodNm[1]).toBe(1600);
    expect(design.angleDeg[1]).toBeCloseTo(90.0, 5);

    expect(design.active[2]).toBe(0);
    expect(design.periodNm[2]).toBe(0);
    expect(design.angleDeg[2]).toBe(0.0);
  });

  it('supports custom period and angle ranges', () => {
    const data = new Uint8Array([
      0, 0, 0, 255,
      255, 255, 0, 255,
    ]);
    const source: RawImageSource = {
      width: 2,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'custom_ranges.png',
    };

    const design = decodeRgbaContinuous(source, {
      minPeriodNm: 500,
      maxPeriodNm: 1200,
      minAngleDeg: -45,
      maxAngleDeg: 45,
      applyFilter: false,
    });

    expect(design.periodNm[0]).toBe(500);
    expect(design.angleDeg[0]).toBeCloseTo(-45.0, 4);

    expect(design.periodNm[1]).toBe(1200);
    expect(design.angleDeg[1]).toBeCloseTo(45.0, 4);
  });

  it('masked bilateral filter preserves boundaries (valid-only masking)', () => {
    // 3x3 image with only center cell active
    const periodNm = new Uint32Array(9);
    const angleDeg = new Float64Array(9);
    const active = new Uint8Array(9);

    active[4] = 1; // center
    periodNm[4] = 1000;
    angleDeg[4] = 45.0;

    const filtered = applyMaskedBilateralFilter(3, 3, periodNm, angleDeg, active);

    // Center cell should NOT bleed with background zeros
    expect(filtered.periodNm[4]).toBe(1000);
    expect(filtered.angleDeg[4]).toBeCloseTo(45.0, 5);
  });

  it('axial bilateral filter respects 180° orientation symmetry', () => {
    // Check that liftToNearestBranch lifts -89° and +89° correctly
    expect(liftToNearestBranch(89.0, -89.0)).toBeCloseTo(-91.0, 4);
    expect(liftToNearestBranch(-89.0, 89.0)).toBeCloseTo(91.0, 4);

    // Row of active cells transitioning across ±90°
    const width = 5;
    const height = 1;
    const periodNm = new Uint32Array([1000, 1000, 1000, 1000, 1000]);
    const angleDeg = new Float64Array([-88.0, -89.0, -90.0, -91.0, -92.0]);
    const active = new Uint8Array([1, 1, 1, 1, 1]);

    const filtered = applyMaskedBilateralFilter(width, height, periodNm, angleDeg, active, 3, 50.0, 10.0, 100.0);

    // The center angle should remain near -90°, never flipped to +90°
    expect(filtered.angleDeg[2]).toBeGreaterThanOrEqual(-95.0);
    expect(filtered.angleDeg[2]).toBeLessThanOrEqual(-85.0);
  });

  it('dynamic post-load adjustment in designStore updates design live', () => {
    const data = new Uint8Array([
      0, 0, 0, 255,
      255, 255, 0, 255,
    ]);
    const source: RawImageSource = {
      width: 2,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'store_test.png',
    };

    designStore.loadSource(source, 'RGBA continuous');
    let design = designStore.getDesign();
    expect(design).not.toBeNull();
    expect(design?.periodNm[0]).toBe(400);
    expect(design?.periodNm[1]).toBe(1600);

    // Live update minPeriodNm and maxPeriodNm without re-uploading
    designStore.setRgbaOptions({ minPeriodNm: 600, maxPeriodNm: 1500 });
    design = designStore.getDesign();
    expect(design?.periodNm[0]).toBe(600);
    expect(design?.periodNm[1]).toBe(1500);

    // Toggle filter
    designStore.setRgbaOptions({ applyFilter: false });
    expect(designStore.getRgbaOptions().applyFilter).toBe(false);
  });

  it('handles completely inactive RGBA images cleanly', () => {
    const data = new Uint8Array([
      255, 255, 255, 0, // A=0 (inactive)
      128, 128, 128, 50, // A=50 < 128 (inactive)
    ]);
    const source: RawImageSource = {
      width: 2,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'inactive.png',
    };

    const design = decodeRgbaContinuous(source, { applyFilter: true });
    expect(design.active[0]).toBe(0);
    expect(design.active[1]).toBe(0);
    expect(design.periodNm[0]).toBe(0);
    expect(design.periodNm[1]).toBe(0);
  });

  it('boundary cells do not bleed into background zeros during filtering', () => {
    // 3x3 with col 0 active (period 1500), cols 1 and 2 inactive
    const width = 3;
    const height = 3;
    const periodNm = new Uint32Array(9);
    const angleDeg = new Float64Array(9);
    const active = new Uint8Array(9);

    for (let r = 0; r < 3; r++) {
      const idx = r * 3;
      active[idx] = 1;
      periodNm[idx] = 1500;
      angleDeg[idx] = 45.0;
    }

    const filtered = applyMaskedBilateralFilter(width, height, periodNm, angleDeg, active, 3);
    for (let r = 0; r < 3; r++) {
      const idx = r * 3;
      expect(filtered.periodNm[idx]).toBe(1500);
      expect(filtered.angleDeg[idx]).toBeCloseTo(45.0, 5);
      // Inactive cells must remain untouched
      expect(filtered.periodNm[idx + 1]).toBe(0);
      expect(filtered.periodNm[idx + 2]).toBe(0);
    }
  });

  it('decodes RGBA continuous with roundIntegerAngles=true to exact integer angles', () => {
    // Pixel 0: G=64 -> -90 + 64/255 * 180 = -44.8235... deg
    // Pixel 1: G=191 -> -90 + 191/255 * 180 = +44.8235... deg
    // Pixel 2: Inactive A=0 -> angle 0
    const data = new Uint8Array([
      128, 64, 0, 255,
      128, 191, 0, 255,
      128, 64, 0, 0,
    ]);
    const source: RawImageSource = {
      width: 3,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'round_test.png',
    };

    const designUnrounded = decodeRgbaContinuous(source, { applyFilter: false, roundIntegerAngles: false });
    expect(designUnrounded.angleDeg[0]).not.toBe(-45);
    expect(designUnrounded.angleDeg[0]).toBeCloseTo(-44.8235, 3);

    const designRounded = decodeRgbaContinuous(source, { applyFilter: false, roundIntegerAngles: true });
    expect(designRounded.angleDeg[0]).toBe(-45);
    expect(designRounded.angleDeg[1]).toBe(45);
    expect(designRounded.angleDeg[2]).toBe(0);
  });

  it('rounds integer angles after filtering when both applyFilter and roundIntegerAngles are enabled', () => {
    const data = new Uint8Array([
      128, 50, 0, 255,
      128, 70, 0, 255,
      128, 90, 0, 255,
    ]);
    const source: RawImageSource = {
      width: 3,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'filter_round_test.png',
    };

    const design = decodeRgbaContinuous(source, { applyFilter: true, roundIntegerAngles: true });
    for (let i = 0; i < 3; i++) {
      expect(Number.isInteger(design.angleDeg[i])).toBe(true);
    }
  });

  it('updates design live when roundIntegerAngles is toggled in designStore', () => {
    const data = new Uint8Array([
      128, 64, 0, 255,
      128, 191, 0, 255,
    ]);
    const source: RawImageSource = {
      width: 2,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'store_round_test.png',
    };

    designStore.loadSource(source, 'RGBA continuous');
    let design = designStore.getDesign();
    expect(design).not.toBeNull();
    expect(design?.angleDeg[0]).not.toBe(-45);

    // Toggle roundIntegerAngles to true
    designStore.setRgbaOptions({ roundIntegerAngles: true });
    expect(designStore.getRgbaOptions().roundIntegerAngles).toBe(true);
    design = designStore.getDesign();
    expect(design?.angleDeg[0]).toBe(-45);
    expect(design?.angleDeg[1]).toBe(45);

    // Toggle back to false
    designStore.setRgbaOptions({ roundIntegerAngles: false });
    expect(designStore.getRgbaOptions().roundIntegerAngles).toBe(false);
    design = designStore.getDesign();
    expect(design?.angleDeg[0]).not.toBe(-45);
  });

  it('decodes RGBA continuous with roundPeriod50Nm=true to exact multiples of 50 nm', () => {
    // Pixel 0: R=5 -> 400 + 5/255 * 1200 = 423.53 nm -> 424 nm -> rounded to 400 nm
    // Pixel 1: R=15 -> 400 + 15/255 * 1200 = 470.59 nm -> 471 nm -> rounded to 450 nm
    // Pixel 2: R=25 -> 400 + 25/255 * 1200 = 517.65 nm -> 518 nm -> rounded to 500 nm
    // Pixel 3: Inactive A=0 -> remains 0
    const data = new Uint8Array([
      5, 0, 0, 255,
      15, 0, 0, 255,
      25, 0, 0, 255,
      5, 0, 0, 0,
    ]);
    const source: RawImageSource = {
      width: 4,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'round_period_test.png',
    };

    const designUnrounded = decodeRgbaContinuous(source, { applyFilter: false, roundPeriod50Nm: false });
    expect(designUnrounded.periodNm[0]).toBe(424);
    expect(designUnrounded.periodNm[1]).toBe(471);
    expect(designUnrounded.periodNm[2]).toBe(518);
    expect(designUnrounded.periodNm[3]).toBe(0);

    const designRounded = decodeRgbaContinuous(source, { applyFilter: false, roundPeriod50Nm: true });
    expect(designRounded.periodNm[0]).toBe(400);
    expect(designRounded.periodNm[1]).toBe(450);
    expect(designRounded.periodNm[2]).toBe(500);
    expect(designRounded.periodNm[3]).toBe(0);
  });

  it('rounds period to 50 nm after filtering when both applyFilter and roundPeriod50Nm are enabled', () => {
    const data = new Uint8Array([
      10, 0, 0, 255,
      20, 0, 0, 255,
      30, 0, 0, 255,
    ]);
    const source: RawImageSource = {
      width: 3,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'filter_round_period_test.png',
    };

    const design = decodeRgbaContinuous(source, { applyFilter: true, roundPeriod50Nm: true });
    for (let i = 0; i < 3; i++) {
      expect(design.periodNm[i] % 50).toBe(0);
      expect(design.periodNm[i]).toBeGreaterThan(0);
    }
  });

  it('updates design live when roundPeriod50Nm is toggled in designStore', () => {
    designStore.setRgbaOptions({ minPeriodNm: 400, maxPeriodNm: 1600, applyFilter: false, roundPeriod50Nm: false });
    const data = new Uint8Array([
      5, 0, 0, 255,
      15, 0, 0, 255,
    ]);
    const source: RawImageSource = {
      width: 2,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'store_round_period_test.png',
    };

    designStore.loadSource(source, 'RGBA continuous');
    let design = designStore.getDesign();
    expect(design).not.toBeNull();
    expect(design?.periodNm[0]).not.toBe(400);

    // Toggle roundPeriod50Nm to true
    designStore.setRgbaOptions({ roundPeriod50Nm: true });
    expect(designStore.getRgbaOptions().roundPeriod50Nm).toBe(true);
    design = designStore.getDesign();
    expect(design?.periodNm[0]).toBe(400);
    expect(design?.periodNm[1]).toBe(450);

    // Toggle back to false
    designStore.setRgbaOptions({ roundPeriod50Nm: false });
    expect(designStore.getRgbaOptions().roundPeriod50Nm).toBe(false);
    design = designStore.getDesign();
    expect(design?.periodNm[0]).not.toBe(400);
  });

  it('correctly rounds half-away-from-zero matching Python contract', () => {
    expect(roundHalfAwayFromZero(0.5)).toBe(1);
    expect(roundHalfAwayFromZero(-0.5)).toBe(-1);
    expect(roundHalfAwayFromZero(1.5)).toBe(2);
    expect(roundHalfAwayFromZero(-1.5)).toBe(-2);
    expect(roundHalfAwayFromZero(2.4)).toBe(2);
    expect(roundHalfAwayFromZero(2.6)).toBe(3);
    expect(roundHalfAwayFromZero(-2.4)).toBe(-2);
    expect(roundHalfAwayFromZero(-2.6)).toBe(-3);
    expect(roundHalfAwayFromZero(0)).toBe(0);
    expect(Object.is(roundHalfAwayFromZero(-0.0), 0)).toBe(true);
    expect(Object.is(roundHalfAwayFromZero(-0.1), 0)).toBe(true);
  });

  it('decodes 16-bit RGBA with roundPeriod50Nm=true', () => {
    // 16-bit data:
    // Pixel 0: R=13653 -> 400 + (13653 / 65535) * 1200 = 650.003 nm -> 650 nm
    // Pixel 1: R=12000 -> 400 + (12000 / 65535) * 1200 = 619.72 nm -> 600 nm
    // Pixel 2: inactive A=0 -> 0
    const data = new Uint16Array([
      13653, 0, 0, 65535,
      12000, 0, 0, 65535,
      13653, 0, 0, 0,
    ]);
    const source: RawImageSource = {
      width: 3,
      height: 1,
      channels: 4,
      bitDepth: 16,
      data,
      filename: '16bit_round_period.png',
    };

    const design = decodeRgbaContinuous(source, { applyFilter: false, roundPeriod50Nm: true });
    expect(design.periodNm[0]).toBe(650);
    expect(design.periodNm[1]).toBe(600);
    expect(design.periodNm[2]).toBe(0);
  });

  it('correctly applies both roundPeriod50Nm and roundIntegerAngles simultaneously', () => {
    // Pixel 0: R=5 (~424nm -> 400nm), G=64 (~ -44.82 deg -> -45 deg)
    const data = new Uint8Array([
      5, 64, 0, 255,
      15, 191, 0, 255,
    ]);
    const source: RawImageSource = {
      width: 2,
      height: 1,
      channels: 4,
      bitDepth: 8,
      data,
      filename: 'joint_round.png',
    };

    const design = decodeRgbaContinuous(source, {
      applyFilter: false,
      roundPeriod50Nm: true,
      roundIntegerAngles: true,
    });
    expect(design.periodNm[0]).toBe(400);
    expect(design.angleDeg[0]).toBe(-45);
    expect(design.periodNm[1]).toBe(450);
    expect(design.angleDeg[1]).toBe(45);
  });
});
