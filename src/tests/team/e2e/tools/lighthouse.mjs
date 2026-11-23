// Lighthouse (accessibility, best practices, SEO) on each key screen while logged in as the manager.
//
// Usage (from src/tests/team/e2e, with the SQE server running):
//   node tools/lighthouse.mjs before        -> local/sqe/evidence/lighthouse/before/
//   node tools/lighthouse.mjs after
//
// How the login is shared: Playwright launches a *persistent* Chromium profile (its default browser context)
// with a remote debugging port, logs in, and Lighthouse connects to that same browser. disableStorageReset
// stops Lighthouse from clearing the session cookie before it loads the page.
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';
import lighthouse from 'lighthouse';

const PHASE = process.argv[2] || 'before';
const RUNS = Number(process.env.LH_RUNS || 3);
const PORT = 9222;
const root = new URL('../../../../../', import.meta.url);
const fixtures = JSON.parse(await readFile(new URL('local/sqe/windows/fixtures.json', root), 'utf8'));
const outDir = new URL(`local/sqe/evidence/lighthouse/${PHASE}/`, root);
const profile = new URL('local/sqe/lighthouse-profile/', root);

const base = `${fixtures.baseUrl}/control/event/${fixtures.organizer}/${fixtures.event}/orders/`;
const SCREENS = [
    { id: 'S1-order-detail', url: `${base}${fixtures.orders.m3_lh_paid}/` },
    { id: 'S2-mark-paid-form', url: `${base}${fixtures.orders.m3_lh_pending}/transition?status=p` },
    { id: 'S3-cancel-form', url: `${base}${fixtures.orders.m3_lh_paid}/transition?status=c` },
];

const config = {
    extends: 'lighthouse:default',
    settings: {
        onlyCategories: ['accessibility', 'best-practices', 'seo'],
        formFactor: 'desktop',
        screenEmulation: { mobile: false, width: 1350, height: 940, deviceScaleFactor: 1, disabled: false },
        throttlingMethod: 'provided',
        disableStorageReset: true,
    },
};

const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

await rm(profile, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });
const context = await chromium.launchPersistentContext(profile.pathname.replace(/^\/([A-Za-z]:)/, '$1'), {
    headless: true, args: [`--remote-debugging-port=${PORT}`],
});

try {
    const page = await context.newPage();
    const manager = fixtures.roles.manager;
    await page.goto(`${fixtures.baseUrl}/control/login`);
    await page.getByLabel('Email', { exact: true }).fill(manager.email);
    await page.getByLabel('Password', { exact: true }).fill(manager.password);
    await page.getByRole('button', { name: 'Log in', exact: true }).click();
    await page.waitForURL((url) => !url.pathname.startsWith('/control/login'));

    const summary = {};
    for (const screen of SCREENS) {
        const scores = { accessibility: [], 'best-practices': [], seo: [] };
        for (let run = 1; run <= RUNS; run++) {
            const result = await lighthouse(screen.url, { port: PORT, output: ['json', 'html'] }, config);
            if (new URL(result.lhr.finalDisplayedUrl).pathname.startsWith('/control/login')) {
                throw new Error(`${screen.id}: Lighthouse was redirected to the login page; the session was not shared.`);
            }
            const [json, html] = result.report;
            await writeFile(new URL(`${screen.id}-run${run}.json`, outDir), json);
            await writeFile(new URL(`${screen.id}-run${run}.html`, outDir), html);
            for (const key of Object.keys(scores)) scores[key].push(Math.round(result.lhr.categories[key].score * 100));
        }
        summary[screen.id] = Object.fromEntries(Object.entries(scores).map(([k, v]) => [k, { runs: v, median: median(v) }]));
        console.log(screen.id, JSON.stringify(summary[screen.id]));
    }
    await writeFile(new URL('summary.json', outDir), JSON.stringify({ phase: PHASE, runs: RUNS, screens: summary }, null, 2));
} finally {
    await context.close();
}
