import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test.describe('UI/UX Bug Remediation Regressions', () => {
  test('BUG-01: slider pointerdown followed by window pointerup outside slider clears interaction state and unblocks sync', async ({ page }) => {
    await page.goto('./?showcase=1');

    const slider = page.getByRole('slider', { name: 'Light Azimuth ° slider', exact: true });
    await slider.scrollIntoViewIfNeeded();
    const box = await slider.boundingBox();
    expect(box).not.toBeNull();

    await page.mouse.move(box!.x + box!.width * 0.5, box!.y + box!.height * 0.5);
    await page.mouse.down();

    await expect
      .poll(() => page.evaluate(() => (window as any).__DOT_EBL_MODULES__.sceneStore.getIsInteracting()))
      .toBe(true);
    await expect(page.locator('.badge-quality')).toContainText('[Interacting]');

    // Release pointer well outside the slider
    await page.mouse.move(5, 5);
    await page.mouse.up();

    await expect
      .poll(() => page.evaluate(() => (window as any).__DOT_EBL_MODULES__.sceneStore.getIsInteracting()))
      .toBe(false);
    await expect(page.locator('.badge-quality')).not.toContainText('[Interacting]');

    // Verify SceneControls sync is unblocked
    await page.getByRole('button', { name: 'Overhead', exact: true }).click();
    await expect(page.getByRole('spinbutton', { name: 'Light Elevation ° numeric value', exact: true })).toHaveValue('89.9');
  });

  test('BUG-02: keystroke-by-keystroke typing in Light Azimuth avoids clobbering and blur clamps/restores cleanly', async ({ page }) => {
    await page.goto('./?showcase=1');

    const azInput = page.getByRole('spinbutton', { name: 'Light Azimuth ° numeric value', exact: true });
    await azInput.click();
    await azInput.selectText();
    await page.keyboard.type('1', { delay: 15 });
    await page.keyboard.type('3', { delay: 15 });
    await page.keyboard.type('5', { delay: 15 });

    // Value remains '135' while typing without premature '.0' clobbering
    await expect(azInput).toHaveValue('135');

    // Blur formats cleanly
    await azInput.press('Tab');
    await expect(azInput).toHaveValue('135.0');

    // Clearing and blurring restores last valid value
    await azInput.click();
    await azInput.selectText();
    await page.keyboard.press('Backspace');
    await expect(azInput).toHaveValue('');
    await azInput.press('Tab');
    await expect(azInput).toHaveValue('135.0');

    // Out-of-range values clamp on blur
    await azInput.click();
    await azInput.selectText();
    await page.keyboard.type('-20');
    await azInput.press('Tab');
    await expect(azInput).toHaveValue('0.0');

    const elInput = page.getByRole('spinbutton', { name: 'Light Elevation ° numeric value', exact: true });
    await elInput.click();
    await elInput.selectText();
    await page.keyboard.type('999');
    await elInput.press('Tab');
    await expect(elInput).toHaveValue('89.0');
  });

  test('BUG-03: Source Image tab renders uploaded image pixels and renders XSS-crafted filenames safely', async ({ page }) => {
    await page.goto('./');

    // Upload valid fixture
    await page.locator('input[type="file"]').first().setInputFiles('tests/fixtures/hls_test.png');
    await page.getByRole('dialog').getByRole('combobox').selectOption('Holtida legacy HLS');
    await page.getByRole('button', { name: 'Import', exact: true }).click();

    await expect(page.locator('.workbench-container')).toBeVisible();
    await page.getByRole('tab', { name: 'Source Image', exact: true }).click();

    const sourcePanel = page.locator('.map-source');
    await expect(sourcePanel).toBeVisible();
    await expect(sourcePanel.getByRole('button', { name: 'Download PNG', exact: true })).toBeEnabled();
    await expect(sourcePanel.locator('.map-legend')).toContainText('hls_test.png');

    // Verify canvas has non-uniform pixel content
    const colorCount = await page.evaluate(() => {
      const canvas = document.querySelector('.map-source .map-canvas') as HTMLCanvasElement;
      const ctx = canvas.getContext('2d')!;
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      const seen = new Set<string>();
      for (let i = 0; i < data.length; i += 4) {
        seen.add(`${data[i]},${data[i + 1]},${data[i + 2]}`);
        if (seen.size > 4) break;
      }
      return { width: canvas.width, height: canvas.height, distinct: seen.size };
    });
    expect(colorCount.width).toBeGreaterThan(1);
    expect(colorCount.height).toBeGreaterThan(1);
    expect(colorCount.distinct).toBeGreaterThan(1);

    // Upload with an XSS-crafted filename
    const hlsBytes = await readFile('tests/fixtures/hls_test.png');
    const xssName = '<img src=x onerror=window.__xss=1>.png';
    await page.locator('.design-controls input[type="file"]').setInputFiles({
      name: xssName,
      mimeType: 'image/png',
      buffer: hlsBytes,
    });

    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText(xssName);
    expect(await dialog.locator('img').count()).toBe(0);

    await dialog.getByRole('combobox').selectOption('Holtida legacy HLS');
    await page.getByRole('button', { name: 'Import', exact: true }).click();

    await expect(sourcePanel.locator('.map-legend')).toContainText(xssName);
    expect(await sourcePanel.locator('.map-legend img').count()).toBe(0);
    expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined();
  });

  test('BUG-04: hides native file input, disables bilateral sliders when unchecked, and hides Retry on RGBA min>=max error', async ({ page }) => {
    await page.goto('./');

    // Upload image with RGBA continuous profile
    await page.locator('input[type="file"]').first().setInputFiles('tests/fixtures/hls_test.png');
    await page.getByRole('dialog').getByRole('combobox').selectOption('RGBA continuous');
    await page.getByRole('button', { name: 'Import', exact: true }).click();
    await expect(page.locator('.workbench-container')).toBeVisible();

    // Native file input inside DesignControls is hidden
    const nativeFileInput = page.locator('.design-controls input[type="file"]');
    await expect(nativeFileInput).toHaveCount(1);
    await expect(nativeFileInput).not.toBeVisible();

    // Uncheck Smooth Gradients -> 4 bilateral filter sliders disabled
    const smoothCheck = page.getByLabel('Smooth Gradients', { exact: true });
    await expect(smoothCheck).toBeChecked();
    for (const name of ['Filter diameter', 'Spatial sigma', 'Period sigma', 'Angle sigma']) {
      await expect(page.getByRole('slider', { name: new RegExp(`^${name}`) })).toBeEnabled();
    }

    await smoothCheck.uncheck();
    for (const name of ['Filter diameter', 'Spatial sigma', 'Period sigma', 'Angle sigma']) {
      await expect(page.getByRole('slider', { name: new RegExp(`^${name}`) })).toBeDisabled();
      await expect(page.getByRole('spinbutton', { name: new RegExp(`^${name}`) })).toBeDisabled();
    }

    // Trigger RGBA min >= max validation error
    const minPeriodNum = page.getByRole('spinbutton', { name: /Min Period \(nm\).*numeric/ });
    await minPeriodNum.fill('1800');
    await minPeriodNum.press('Tab');

    await expect(page.getByRole('alert')).toContainText('Minimum must be less than maximum');
    await expect(page.locator('.design-controls').getByRole('button', { name: 'Retry', exact: true })).toBeHidden();
    await expect(page.locator('.design-controls').getByRole('button', { name: 'Continue with retained design', exact: true })).toBeVisible();
  });

  test('BUG-05: Perspective Capture PNG downloads a valid non-empty PNG in Flat 2D mode', async ({ page }) => {
    await page.goto('./?showcase=1');

    await expect(page.getByRole('button', { name: 'Flat 2D Reference', exact: true })).toHaveClass(/btn-active/);
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Perspective Capture PNG', exact: true }).click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toMatch(/^perspective_capture_\d+x\d+\.png$/);
    const bytes = await readFile((await download.path())!);
    expect(bytes.length).toBeGreaterThan(1000);
    expect(Array.from(bytes.subarray(0, 4))).toEqual([0x89, 0x50, 0x4e, 0x47]);
  });

  test('BUG-06: clicking outside hologram does not change cell, pointerleave resets pill, Row input not overwritten during sweep', async ({ page }) => {
    await page.goto('./?showcase=1');

    const rowInput = page.getByLabel('Row (zero-based)', { exact: true });
    await rowInput.fill('10');
    await rowInput.press('Tab');
    await expect(page.locator('.cell-selection output')).toContainText('Cell (10, 0)');

    const flatCanvas = page.locator('.flat-canvas');
    const box = (await flatCanvas.boundingBox())!;

    // Click near top-left corner outside the 90%-fitted square hologram
    await page.mouse.click(box.x + 2, box.y + 2);
    await expect(page.locator('.cell-selection output')).toContainText('Cell (10, 0)');

    // Hover center -> probe updates; move outside canvas -> resets hover pill
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
    await expect(page.locator('.hover-probe-pill')).toHaveClass(/has-data/);
    await expect(page.locator('.hover-probe-pill')).toContainText('Cell (');

    await page.mouse.move(0, 0);
    await expect(page.locator('.hover-probe-pill')).not.toHaveClass(/has-data/);
    await expect(page.locator('.hover-probe-pill')).toHaveText('Hover over surface to inspect cell parameters');

    // Start Auto Sweep, type into Row input without blurring, verify not overwritten
    await page.locator('#btn-sweep-azimuth').click();
    await expect(page.locator('#btn-sweep-azimuth')).toHaveAttribute('aria-pressed', 'true');

    await rowInput.click();
    await rowInput.selectText();
    await page.keyboard.type('42');
    await page.waitForTimeout(250);
    await expect(rowInput).toHaveValue('42');

    await page.locator('#btn-sweep-azimuth').click();
  });

  test('BUG-07: Preset Gallery stops active Auto Sweep Azimuth and Return to Workbench restores workbench', async ({ page }) => {
    await page.goto('./?showcase=1');

    const sweepBtn = page.locator('#btn-sweep-azimuth');
    await sweepBtn.click();
    await expect(sweepBtn).toHaveAttribute('aria-pressed', 'true');

    const getPrimaryPos = () => page.evaluate(() => (window as any).__DOT_EBL_MODULES__.sceneStore.getPrimaryLight().pos);
    const posBefore = await getPrimaryPos();
    await expect.poll(getPrimaryPos).not.toEqual(posBefore);

    // Navigate to Preset Gallery
    await page.locator('#header-welcome-btn').click();
    await expect(page.locator('.welcome-container')).toBeVisible();
    await expect(page.locator('.workbench-container')).toBeHidden();
    await expect(sweepBtn).toHaveAttribute('aria-pressed', 'false');

    const posAtGallery = await getPrimaryPos();
    await page.waitForTimeout(200);
    expect(await getPrimaryPos()).toEqual(posAtGallery);

    // Return to Workbench
    const returnBtn = page.locator('#header-workbench-btn');
    await expect(returnBtn).toBeVisible();
    await returnBtn.click();

    await expect(page.locator('.workbench-container')).toBeVisible();
    await expect(page.locator('.welcome-container')).toBeHidden();
    await expect(returnBtn).toBeHidden();
  });

  test('BUG-08: Retry preview immediately re-enables Optical Preview PNG and Center checkbox is compact', async ({ page }) => {
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      (window as any).__deny = true;
      HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: any, ...args: any[]) {
        if ((window as any).__deny && String(type).includes('webgl')) return null;
        return (original as any).call(this, type, ...args);
      } as any;
    });

    await page.goto('./');
    await page.locator('.preset-card').first().click();

    const retryBtn = page.getByRole('button', { name: 'Retry preview', exact: true });
    const flatOpticalBtn = page.getByRole('button', { name: 'Optical Preview PNG (1:1)', exact: true });
    await expect(retryBtn).toBeVisible();
    await expect(flatOpticalBtn).toBeDisabled();

    // Restore WebGL and click Retry preview without moving mouse over ExportControls
    await page.evaluate(() => {
      (window as any).__deny = false;
    });
    await retryBtn.click();

    await expect(page.locator('.preview-recovery')).toBeHidden();
    await expect(flatOpticalBtn).toBeEnabled();
    await expect(page.locator('.export-controls')).not.toContainText('Optical captures are unavailable');

    // Center full grid at (0, 0) checkbox width < 40px
    await page.getByText('EBL Lithography Fabrication', { exact: true }).click();
    const centerCheckbox = page.getByLabel('Center full grid at (0, 0)', { exact: true });
    await expect(centerCheckbox).toBeVisible();
    const checkboxBox = (await centerCheckbox.boundingBox())!;
    expect(checkboxBox.width).toBeGreaterThan(0);
    expect(checkboxBox.width).toBeLessThan(40);
  });

  test('BUG-10: importing an image from Welcome screen focuses Workbench heading', async ({ page }) => {
    await page.goto('./');

    await page.locator('.welcome-container input[type="file"]').setInputFiles('tests/fixtures/hls_test.png');
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('combobox').selectOption('Holtida legacy HLS');
    await dialog.getByRole('button', { name: 'Import', exact: true }).click();

    await expect(page.locator('.workbench-container')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Design & Ingestion' })).toBeFocused();
  });

  test('BUG-11: range slider shows visible :focus-visible outline and cell-selection does not overlap flat-canvas', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('./?showcase=1');

    // Keyboard-tab from Upload Design button to the first range slider
    await page.getByRole('button', { name: /Upload Design/ }).focus();
    let hitSlider = false;
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab');
      hitSlider = await page.evaluate(() => document.activeElement?.matches('input[type="range"].form-range') ?? false);
      if (hitSlider) break;
    }
    expect(hitSlider).toBe(true);

    const outline = await page.evaluate(() => {
      const s = getComputedStyle(document.activeElement!);
      return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) };
    });
    expect(outline.style).not.toBe('none');
    expect(outline.width).toBeGreaterThanOrEqual(2);

    // Check no overlap between .flat-canvas and .cell-selection at 1440x900 and 390x844
    for (const [width, height] of [
      [1440, 900],
      [390, 844],
    ] as const) {
      await page.setViewportSize({ width, height });
      const flatBox = (await page.locator('.flat-canvas').boundingBox())!;
      const selBox = (await page.locator('.cell-selection').boundingBox())!;
      expect(flatBox.height).toBeGreaterThan(0);
      expect(selBox.height).toBeGreaterThan(0);
      expect(flatBox.y + flatBox.height).toBeLessThanOrEqual(selBox.y + 1);
    }
  });
});
