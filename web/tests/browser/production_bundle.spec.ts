import { test, expect } from '@playwright/test';

test.describe('Production Bundle and Nested Base Path', () => {
  test('loads assets with relative paths without console errors or 404s', async ({ page }) => {
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    page.on('pageerror', error => consoleErrors.push(error.message));
    page.on('response', response => {
      if (response.status() >= 400) failedRequests.push(`${response.status()} ${response.url()}`);
    });

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    page.on('requestfailed', (req) => {
      failedRequests.push(`${req.url()}: ${req.failure()?.errorText}`);
    });

    await page.goto('./');

    // Check page title and structure
    await expect(page).toHaveTitle(/Dot EBL Preview/);
    await expect(page.locator('.brand-title')).toHaveText('Dot EBL Preview');

    await page.reload();
    await expect(page.locator('.brand-title')).toHaveText('Dot EBL Preview');

    // No asset load failures or unhandled console errors
    expect(failedRequests).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
