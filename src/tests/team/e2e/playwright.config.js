import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

const repoRoot = fileURLToPath(new URL('../../../../', import.meta.url));
const evidence = fileURLToPath(new URL('../../../../local/sqe/evidence/', import.meta.url));
const baseURL = 'http://127.0.0.1:18081';

process.env.PLAYWRIGHT_BROWSERS_PATH ??= fileURLToPath(new URL('../../../../local/sqe/browsers/', import.meta.url));

export default defineConfig({
    testDir: '.',
    workers: 1,
    retries: 0,
    outputDir: evidence + 'playwright-results',
    reporter: [
        ['list'],
        ['html', { outputFolder: evidence + 'playwright-report', open: 'never' }],
    ],
    use: {
        baseURL, locale: 'en-US', timezoneId: 'UTC', actionTimeout: 10_000, trace: 'retain-on-failure',
        // Optional OWASP ZAP passive scan: set ZAP_PROXY=http://127.0.0.1:8090. Chromium bypasses proxies for
        // loopback hosts by default, so <-loopback> is required or ZAP sees no traffic.
        ...(process.env.ZAP_PROXY ? {
            proxy: { server: process.env.ZAP_PROXY, bypass: '<-loopback>' },
            launchOptions: { args: ['--proxy-bypass-list=<-loopback>'] },
        } : {}),
    },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
    webServer: {
        command: 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\sqe\\windows.ps1 serve',
        cwd: repoRoot,
        url: baseURL + '/control/login',
        reuseExistingServer: process.env.SQE_REUSE_SERVER === '1',
        timeout: 60_000,
    },
});
