import { expect, test } from '@playwright/test';
import { getSpectralConfig, type QualityLevel } from '../../lib/optics/tables';
import type { LightSettings } from '../../lib/optics/glRenderer';

// Allow reproducing driver-specific differences alongside deterministic SwiftShader CI runs.
if (process.env.TEST_NATIVE_GPU === '1') test.use({ launchOptions: { args: ['--enable-webgl'] } });
if (process.env.TEST_EDGE === '1') test.use({ channel: 'msedge' });

const periods = [700, 850, 1000, 1200];
const angles = [-90, -45, 0, 45];
const secondary: LightSettings = { pos: { x: 229.43, y: 0, z: 327.66 }, sourceRadiusMm: 60, intensity: 0.8 };
const primary = (az: number, intensity = 1): LightSettings => ({
  pos: { x: 229.43 * Math.cos(az * Math.PI / 180), y: 229.43 * Math.sin(az * Math.PI / 180), z: 327.66 },
  sourceRadiusMm: 40, intensity,
});

// Independent double-precision implementation of the documented optical equations.
// Gamut intersection uses the ray from white to chromaticity and triangle edges.
function reference(lights: LightSettings[], quality: QualityLevel, single: boolean): number[] {
  const spec = getSpectralConfig(quality);
  const cross = (a: number[], b: number[]) => a[0] * b[1] - a[1] * b[0];
  const rgb: number[] = [];
  for (let row = 0; row < 4; row++) for (let col = 0; col < 4; col++) {
    const world = [(col - 1.5) * 0.02, -(row - 1.5) * 0.02, 0];
    const cam = world.map((v, i) => (i === 2 ? 300 : 0) - v);
    const camLength = Math.hypot(...cam);
    const camera = cam.map(v => v / camLength);
    const detector = 10 / camLength;
    const angle = angles[row] * Math.PI / 180;
    const g = [-Math.sin(angle), Math.cos(angle)];
    const xyz = [0, 0, 0];
    for (const source of lights) {
      const v = [source.pos.x - world[0], source.pos.y - world[1], source.pos.z];
      const length = Math.hypot(...v);
      const light = v.map(x => x / length);
      for (let band = 0; band < spec.numBands; band++) {
        const wavelength = spec.wavelengthsNm[band];
        const beam = (0.5 * wavelength / 20000) ** 2 + 0.25 * (source.sourceRadiusMm / length) ** 2;
        const variance = beam + 0.25 * detector ** 2;
        for (const order of single ? [1] : [-1, 1]) {
          const ax = -light[0] + order * wavelength / periods[col] * g[0];
          const ay = -light[1] + order * wavelength / periods[col] * g[1];
          if (ax * ax + ay * ay > 1) continue;
          const az = Math.sqrt(1 - ax * ax - ay * ay);
          const theta = Math.acos(Math.max(-1, Math.min(1, ax * camera[0] + ay * camera[1] + az * camera[2])));
          const weight = source.intensity * Math.max(0, light[2]) * az *
            (1 - Math.exp(-0.5 * detector ** 2 / beam)) * Math.exp(-0.5 * theta ** 2 / variance);
          for (let c = 0; c < 3; c++) xyz[c] += spec.premultipliedXyz[band * 4 + c] * weight / spec.lightY;
        }
      }
    }
    const total = xyz.reduce((a, b) => a + b, 0);
    if (total < 1e-9) { rgb.push(0, 0, 0); continue; }
    const white = spec.whiteXy;
    const ray = [xyz[0] / total - white[0], xyz[1] / total - white[1]];
    const vertices = [[0.64, 0.33], [0.30, 0.60], [0.15, 0.06]];
    let boundary = Infinity;
    for (let edge = 0; edge < 3; edge++) {
      const a = vertices[edge], b = vertices[(edge + 1) % 3];
      const side = [b[0] - a[0], b[1] - a[1]];
      const offset = [a[0] - white[0], a[1] - white[1]];
      const denominator = cross(ray, side);
      if (Math.abs(denominator) < 1e-12) continue;
      const t = cross(offset, side) / denominator;
      const u = cross(offset, ray) / denominator;
      if (t > 0 && u >= 0 && u <= 1) boundary = Math.min(boundary, t);
    }
    if (boundary < 1) {
      const x = white[0] + 0.99 * boundary * ray[0];
      const y = white[1] + 0.99 * boundary * ray[1];
      xyz[0] = xyz[1] * x / y;
      xyz[2] = xyz[1] * (1 - x - y) / y;
    }
    for (const coefficients of [[3.2404542, -1.5371385, -0.4985314], [-0.969266, 1.8760108, 0.041556], [0.0556434, -0.2040259, 1.0572252]]) {
      const linear = Math.max(0, Math.min(1, coefficients.reduce((sum, c, i) => sum + c * xyz[i], 0)));
      rgb.push(Math.round(255 * (linear <= 0.0031308 ? 12.92 * linear : 1.055 * linear ** (1 / 2.4) - 0.055)));
    }
  }
  return rgb;
}

for (const quality of ['high', 'balanced', 'performance'] as const) for (const single of [false, true]) {
  test(`independent light contributions: ${quality}, single=${single}`, async ({ page }) => {
    await page.goto('./');
    const scenes = [
      [primary(0, 0), secondary], [primary(75, 0), secondary], [primary(180, 0), secondary],
      [secondary], [primary(0)], [primary(75)], [primary(180)],
      [primary(0), secondary], [primary(75), secondary], [primary(180), secondary],
      [secondary, primary(75)], [primary(75)], [primary(75), secondary],
    ];
    const results = await page.evaluate(({ scenes, quality, single, periods, angles }) => {
      const { WebGlDiffractionRenderer } = (window as any).__DOT_EBL_MODULES__;
      const canvas = document.createElement('canvas');
      const renderer = new WebGlDiffractionRenderer(canvas);
      const design = { width: 4, height: 4, pitchNm: 20000,
        periodNm: new Uint32Array(Array.from({ length: 16 }, (_, i) => periods[i % 4])),
        angleDeg: new Float64Array(Array.from({ length: 16 }, (_, i) => angles[Math.floor(i / 4)])),
        active: new Uint8Array(16).fill(1), sourceIdentity: 'multi-light' };
      const gl = renderer.gl as WebGL2RenderingContext;
      const results = scenes.map(lights => {
        renderer.render(design, { lights, quality, diffractionOrders: single ? 'single' : 'both',
          cameraPos: { x: 0, y: 0, z: 300 }, apertureRadiusMm: 10, orientationDeg: 0 }, canvas);
        const program = gl.getParameter(gl.CURRENT_PROGRAM);
        const uniform = (name: string) => {
          const location = gl.getUniformLocation(program, name);
          if (location === null) throw new Error(`Missing uniform ${name}`);
          return gl.getUniform(program, location);
        };
        const uploaded = lights.map((_, i) => ({ pos: Array.from(uniform(`u_light_pos[${i}]`)),
          radius: uniform(`u_source_size_mm[${i}]`), intensity: uniform(`u_light_intensity[${i}]`) }));
        const pixels = new Uint8Array(64);
        gl.readPixels(0, 0, 4, 4, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        const rgb: number[] = [];
        for (let row = 3; row >= 0; row--) for (let col = 0; col < 4; col++) {
          const i = (row * 4 + col) * 4; rgb.push(...pixels.slice(i, i + 3));
        }
        return { rgb, uploaded, count: uniform('u_num_lights'), error: gl.getError() };
      });
      renderer.dispose();
      return results;
    }, { scenes, quality, single, periods, angles });
    results.forEach((result, index) => {
      expect(result.error).toBe(0);
      expect(result.count).toBe(scenes[index].length);
      result.uploaded.forEach((light, i) => {
        const expected = scenes[index][i];
        light.pos.forEach((v, c) => expect(v).toBeCloseTo([expected.pos.x, expected.pos.y, expected.pos.z][c], 3));
        expect(light.radius).toBeCloseTo(expected.sourceRadiusMm, 5);
        expect(light.intensity).toBeCloseTo(expected.intensity, 5);
      });
      const expected = reference(scenes[index], quality, single);
      expect(Math.max(...result.rgb.map((v, i) => Math.abs(v - expected[i])))).toBeLessThanOrEqual(4);
    });
    expect(Math.max(...results[0].rgb)).toBeGreaterThan(10);
    for (const index of [1, 2, 3]) expect(results[index].rgb).toEqual(results[0].rgb);
    expect(Math.max(...results[8].rgb.map((v, i) => Math.abs(v - results[10].rgb[i])))).toBeLessThanOrEqual(1);
    expect(results[12].rgb).toEqual(results[8].rgb);
  });
}

test('flat controls and auto sweep preserve secondary settings', async ({ page }) => {
  await page.goto('./?showcase=1');
  await page.getByText('Secondary Fill Light', { exact: true }).click();
  const snapshot = () => page.evaluate(() => (window as any).__DOT_EBL_MODULES__.sceneStore.getSecondaryLight());
  const initial = await snapshot();
  const azimuth = page.getByRole('slider', { name: 'Light Azimuth ° slider', exact: true });
  await azimuth.dispatchEvent('pointerdown');
  await azimuth.fill('175');
  await azimuth.dispatchEvent('input');
  expect(await snapshot()).toEqual(initial);
  await azimuth.dispatchEvent('pointerup');
  const primaryPosition = () => page.evaluate(() => (window as any).__DOT_EBL_MODULES__.sceneStore.getPrimaryLight().pos);
  const before = await primaryPosition();
  await page.locator('#btn-sweep-azimuth').click();
  await expect.poll(primaryPosition).not.toEqual(before);
  expect(await snapshot()).toEqual(initial);
  await page.locator('#btn-sweep-azimuth').click();
  expect(await snapshot()).toEqual(initial);
  await expect(page.getByRole('button', { name: '3D Perspective', exact: true })).toBeDisabled();
});

test('showcase at equal 135 and 45 degree illumination has a symmetric spectral annulus', async ({ page }) => {
  await page.goto('./?showcase=1');
  await page.getByText('Secondary Fill Light', { exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Light Azimuth ° numeric value', exact: true }).fill('135');
  await page.getByRole('spinbutton', { name: 'Fill Light Azimuth ° numeric value', exact: true }).fill('45');
  await page.getByRole('spinbutton', { name: 'Fill Intensity  numeric value', exact: true }).fill('1');
  const result = await page.evaluate(() => {
    const { WebGlDiffractionRenderer, designStore, sceneStore } = (window as any).__DOT_EBL_MODULES__;
    const canvas = document.createElement('canvas');
    const renderer = new WebGlDiffractionRenderer(canvas);
    const design = designStore.getDesign();
    const params = sceneStore.getRenderParams();
    const render = (lights: any[]) => {
      renderer.render(design, { ...params, lights }, canvas);
      const raw = new Uint8Array(256 * 256 * 4);
      renderer.gl.readPixels(0, 0, 256, 256, renderer.gl.RGBA, renderer.gl.UNSIGNED_BYTE, raw);
      return raw;
    };
    const combined = render(params.lights);
    const swapped = render([...params.lights].reverse());
    const a = render([params.lights[0]]), b = render([params.lights[1]]);
    let slotError = 0, annulusError = 0, singleMirrorError = 0;
    for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) {
      const r = Math.hypot(x - 127.5, y - 127.5);
      for (let c = 0; c < 3; c++) {
        const i = (y * 256 + x) * 4 + c;
        const mirror = (y * 256 + 255 - x) * 4 + c;
        slotError = Math.max(slotError, Math.abs(combined[i] - swapped[i]));
        if (r >= 52 && r < 74) {
          annulusError = Math.max(annulusError, Math.abs(combined[i] - combined[mirror]));
          singleMirrorError = Math.max(singleMirrorError, Math.abs(a[i] - b[mirror]));
        }
      }
    }
    renderer.dispose();
    return { slotError, annulusError, singleMirrorError };
  });
  expect(result.slotError).toBeLessThanOrEqual(1);
  expect(result.singleMirrorError).toBeLessThanOrEqual(1);
  expect(result.annulusError).toBeLessThanOrEqual(1);
});
