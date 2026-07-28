import { defineConfig, devices } from '@playwright/test';

const BASE_PORT = Number(process.env.CA_E2E_PORT || 8798);

// Each worker gets its own fully isolated backend instance (own scratch
// $HOME, config, resource roots — see e2e/start-server.sh) so spec files
// can run concurrently instead of serializing through a single shared
// backend whose /api/__e2e_reset would otherwise race between workers.
// e2e/lib/test-base.ts maps each test to its worker's port via
// testInfo.parallelIndex. 4 keeps resource usage predictable across both
// a laptop and a CI runner without needing per-environment tuning.
const WORKERS = 4;

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: WORKERS,
  reporter: 'html',
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: Array.from({ length: WORKERS }, (_, i) => ({
    command: 'bash e2e/start-server.sh',
    url: `http://127.0.0.1:${BASE_PORT + i}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'pipe' as const,
    stderr: 'pipe' as const,
    env: { CA_E2E_PORT: String(BASE_PORT + i) },
  })),
});
