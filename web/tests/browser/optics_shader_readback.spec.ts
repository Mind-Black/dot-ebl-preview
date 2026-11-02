import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';

const FIXTURES_DIR = fileURLToPath(new URL('../fixtures', import.meta.url));

test.describe('WebGL2 Optical Diffraction Shader Readback', () => {
  test('matches Python CPU reference within 4 code values per channel', async ({ page }) => {
    const fixtureData = JSON.parse(
      readFileSync(resolve(FIXTURES_DIR, 'optical_reference_expected.json'), 'utf-8')
    );

    await page.goto('./');

    const result = await page.evaluate((fixture) => {
      const modules = (window as any).__DOT_EBL_MODULES__;
      if (!modules || !modules.WebGlDiffractionRenderer) {
        throw new Error('WebGlDiffractionRenderer not found on window.__DOT_EBL_MODULES__');
      }

      const { WebGlDiffractionRenderer } = modules;
      const offscreen = document.createElement('canvas');
      offscreen.width = fixture.shape[1];
      offscreen.height = fixture.shape[0];

      const renderer = new WebGlDiffractionRenderer(offscreen);

      const periodNm = new Uint32Array(fixture.period_nm.flat());
      const angleDeg = new Float64Array(fixture.angle_deg.flat());
      const active = new Uint8Array(fixture.active.flat());
      const fallbackIntensity = new Float32Array(fixture.fallback_intensity.flat());

      const design = {
        width: fixture.shape[1],
        height: fixture.shape[0],
        pitchNm: fixture.pitch_nm,
        periodNm,
        angleDeg,
        active,
        fallbackIntensity,
        sourceIdentity: 'test-optical-reference',
      };

      const renderParams = {
        cameraPos: {
          x: fixture.scene.camera_pos[0],
          y: fixture.scene.camera_pos[1],
          z: fixture.scene.camera_pos[2],
        },
        apertureRadiusMm: fixture.scene.aperture_mm,
        orientationDeg: fixture.scene.orientation_deg,
        lights: [
          {
            pos: {
              x: fixture.scene.light_pos[0],
              y: fixture.scene.light_pos[1],
              z: fixture.scene.light_pos[2],
            },
            sourceRadiusMm: fixture.scene.source_size_mm,
            intensity: 1.0,
          },
        ],
        quality: 'high',
        downsampleFactor: 1.0,
      };

      renderer.render(design, renderParams, offscreen);

      // Read back pixels directly from WebGL2
      const ctx = offscreen.getContext('2d') || offscreen.getContext('webgl2');
      let pixelData: number[] = [];

      if (ctx instanceof WebGL2RenderingContext) {
        const raw = new Uint8Array(design.width * design.height * 4);
        ctx.readPixels(0, 0, design.width, design.height, ctx.RGBA, ctx.UNSIGNED_BYTE, raw);
        // Note: OpenGL readPixels reads bottom-to-top; flip rows to match top-to-bottom
        for (let row = design.height - 1; row >= 0; row--) {
          for (let col = 0; col < design.width; col++) {
            const idx = (row * design.width + col) * 4;
            pixelData.push(raw[idx], raw[idx + 1], raw[idx + 2]);
          }
        }
      }

      renderer.dispose();
      return { pixelData };
    }, fixtureData);

    const expectedRgb = fixtureData.rgb_values;
    let maxDiff = 0;
    let nonzeroCount = 0;

    let idx = 0;
    for (let r = 0; r < fixtureData.shape[0]; r++) {
      for (let c = 0; c < fixtureData.shape[1]; c++) {
        const expR = expectedRgb[r][c][0];
        const expG = expectedRgb[r][c][1];
        const expB = expectedRgb[r][c][2];

        const actR = result.pixelData[idx++];
        const actG = result.pixelData[idx++];
        const actB = result.pixelData[idx++];

        if (actR > 20 || actG > 20 || actB > 20) nonzeroCount++;

        const diffR = Math.abs(actR - expR);
        const diffG = Math.abs(actG - expG);
        const diffB = Math.abs(actB - expB);

        const cellDiff = Math.max(diffR, diffG, diffB);
        if (cellDiff > maxDiff) maxDiff = cellDiff;
      }
    }

    // Inactive fallback at (0, 0) with fallback_intensity = 0.2 must be exactly round(0.2 * 255) = 51
    const fallbackR = result.pixelData[0];
    const fallbackG = result.pixelData[1];
    const fallbackB = result.pixelData[2];
    expect(fallbackR).toBe(51);
    expect(fallbackG).toBe(51);
    expect(fallbackB).toBe(51);

    // Active illuminated cells have non-zero brightness
    expect(nonzeroCount).toBeGreaterThan(5);

    // Maximum error across all channels must be <= 4 code values (matching desktop test_gl_preview.py)
    expect(maxDiff).toBeLessThanOrEqual(4);
  });

  test('handles zero intensity and rear-side light geometry producing black output', async ({ page }) => {
    await page.goto('./');

    const result = await page.evaluate(() => {
      const { WebGlDiffractionRenderer } = (window as any).__DOT_EBL_MODULES__;
      const offscreen = document.createElement('canvas');
      offscreen.width = 4;
      offscreen.height = 4;
      const renderer = new WebGlDiffractionRenderer(offscreen);

      const design = {
        width: 4,
        height: 4,
        pitchNm: 20000,
        periodNm: new Uint32Array(16).fill(1000),
        angleDeg: new Float64Array(16).fill(0),
        active: new Uint8Array(16).fill(1),
        sourceIdentity: 'test-rear',
      };

      // Rear-side light (Z < 0): cos_inc <= 0
      const renderParams = {
        cameraPos: { x: 0, y: 0, z: 300 },
        apertureRadiusMm: 2.0,
        orientationDeg: 0,
        lights: [{ pos: { x: 0, y: 0, z: -300 }, sourceRadiusMm: 20, intensity: 1.0 }],
        quality: 'balanced',
      };

      renderer.render(design, renderParams, offscreen);
      const gl = offscreen.getContext('webgl2')!;
      const pixels = new Uint8Array(16 * 4);
      gl.readPixels(0, 0, 4, 4, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      renderer.dispose();

      // All RGB components should be 0
      let allBlack = true;
      for (let i = 0; i < 16; i++) {
        if (pixels[i * 4] !== 0 || pixels[i * 4 + 1] !== 0 || pixels[i * 4 + 2] !== 0) {
          allBlack = false;
        }
      }
      return { allBlack };
    });

    expect(result.allBlack).toBe(true);
  });
});
