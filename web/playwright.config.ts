import { defineConfig, devices } from '@playwright/test';

const production = process.env.TEST_PRODUCTION === '1';
const basePath = production ? '/dot-ebl-preview/' : '/';
const port = Number(process.env.TEST_PORT || 3000);

export default defineConfig({
  testDir: 'tests/browser',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${port}${basePath}`,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-webgl'],
        },
      },
    },
    // Edge's native ANGLE backend exposed multi-light errors hidden by SwiftShader.
    ...(process.platform === 'win32' ? [{
      name: 'edge-optics',
      testMatch: /(?:multi_light|optics_shader_readback)\.spec\.ts/,
      use: {
        ...devices['Desktop Edge'],
        channel: 'msedge',
        launchOptions: { args: ['--enable-webgl'] },
      },
    }] : []),
  ],
  webServer: {
    command: production ? `node scripts/serve-production.mjs ${port}` : `npm run dev -- --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}${basePath}`,
    reuseExistingServer: !production && !process.env.CI,
    timeout: 30000,
  },
});
