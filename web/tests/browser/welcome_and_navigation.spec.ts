import { test, expect } from '@playwright/test';

test.describe('Welcome Screen and Workbench Navigation', () => {
  test('displays welcome view on initial visit with upload zone and 4 preset cards', async ({ page }) => {
    await page.goto('./');

    await expect(page.locator('.hero-title')).toContainText('Diffraction Optics & Physical Parameter Inspector');
    await expect(page.locator('#welcome-dropzone')).toBeVisible();

    const presetCards = page.locator('.preset-card');
    await expect(presetCards).toHaveCount(4);
    await expect(presetCards.nth(0)).toContainText('Concentric Test Pattern');
    await expect(presetCards.nth(1)).toContainText('Orthogonal Cross');
    await expect(presetCards.nth(2)).toContainText('Spectral Fan Sweep');
    await expect(presetCards.nth(3)).toContainText('EBL Glyph Emblem');
  });

  test('clicking a preset card smoothly transitions to the dual-viewport workbench', async ({ page }) => {
    await page.goto('./');

    // Click the Concentric Test Pattern card
    await page.locator('.preset-card').nth(0).click();

    // Welcome view is hidden; workbench is visible
    await expect(page.locator('.welcome-container')).toHaveClass(/hidden/);
    await expect(page.locator('.workbench-container')).not.toHaveClass(/hidden/);

    // Verify dual viewport toolbar buttons (perspective and side-by-side disabled for now)
    await expect(page.getByRole('button', { name: '3D Perspective' })).toBeVisible();
    await expect(page.getByRole('button', { name: '3D Perspective' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Flat 2D Reference' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Flat 2D Reference' })).toHaveClass(/btn-active/);
    await expect(page.getByRole('button', { name: 'Side-by-Side' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Side-by-Side' })).toBeDisabled();

    // Verify Inspector tabs
    await expect(page.getByRole('tab', { name: 'Period Map' })).toHaveClass(/active/);
    await expect(page.locator('.map-periods')).toBeVisible();

    // Switch to Angle Map tab
    await page.getByRole('tab', { name: 'Angle Map' }).click();
    await expect(page.locator('.map-angles')).toBeVisible();
    await expect(page.locator('.map-periods')).toBeHidden();

    // Switch to Analytics tab
    await page.getByRole('tab', { name: 'Analytics' }).click();
    await expect(page.locator('.stats-overview-grid')).toBeVisible();
    await expect(page.locator('.stats-overview-grid')).toContainText('128 × 128');

    // Click "Preset Gallery" in header to return to welcome screen
    await page.locator('#header-welcome-btn').click();
    await expect(page.locator('.welcome-container')).not.toHaveClass(/hidden/);
    await expect(page.locator('.workbench-container')).toHaveClass(/hidden/);
  });

  test('collapses responsibly on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('./');

    await expect(page.locator('.hero-title')).toBeVisible();
    await page.locator('.preset-card').nth(1).click();

    await expect(page.locator('.workbench-container')).toBeVisible();
    await expect(page.locator('.dual-viewport-hero')).toBeVisible();
  });
});
