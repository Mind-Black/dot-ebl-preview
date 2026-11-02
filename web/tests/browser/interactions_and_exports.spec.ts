import { test, expect } from '@playwright/test';

test.describe('Interactions, Probing, and Export Downloads', () => {
  test('cell picking on hover updates the status bar pill', async ({ page }) => {
    await page.goto('./');

    // Load Concentric Test Pattern
    await page.locator('.preset-card').nth(0).click();
    await expect(page.locator('.workbench-container')).toBeVisible();

    const canvas = page.locator('.flat-canvas');
    await expect(canvas).toBeVisible();

    // Trigger hover over center of flat canvas
    await canvas.hover();

    // Hover pill should update
    const hoverPill = page.locator('.hover-probe-pill');
    await expect(hoverPill).toHaveClass(/has-data/);
    await expect(hoverPill).toContainText('Period:');
    await expect(hoverPill).toContainText('nm');
  });

  test('export buttons trigger file downloads with appropriate formats', async ({ page }) => {
    await page.goto('./');
    await page.locator('.preset-card').nth(0).click();

    // 1. Export CSV
    const csvDownloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Parameter Distribution (CSV)' }).click();
    const csvDownload = await csvDownloadPromise;
    expect(csvDownload.suggestedFilename()).toMatch(/\.csv$/);

    // 2. Export JSON
    const jsonDownloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Parameter Metadata (JSON)' }).click();
    const jsonDownload = await jsonDownloadPromise;
    expect(jsonDownload.suggestedFilename()).toMatch(/\.json$/);

    // 3. Export Optical PNG
    const pngDownloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Optical Preview PNG (1:1)' }).click();
    const pngDownload = await pngDownloadPromise;
    expect(pngDownload.suggestedFilename()).toMatch(/\.png$/);

    // 4. Export Perspective Capture PNG
    const perspDownloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Perspective Capture PNG' }).click();
    const perspDownload = await perspDownloadPromise;
    expect(perspDownload.suggestedFilename()).toMatch(/\.png$/);
  });
});
