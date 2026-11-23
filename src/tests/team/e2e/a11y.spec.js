// Member 3 accessibility: full axe-core scan of each key screen while logged in as the manager.
// Results go to local/sqe/evidence/a11y/<A11Y_PHASE>/axe-<screen>.json (A11Y_PHASE = before | after).
import { mkdir, writeFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './orders.js';

const PHASE = process.env.A11Y_PHASE || 'before';
const outDir = new URL(`../../../../local/sqe/evidence/a11y/${PHASE}/`, import.meta.url);

export const SCREENS = [
    { id: 'S1-order-detail', alias: 'm3_lh_paid', path: '' },
    { id: 'S2-mark-paid-form', alias: 'm3_lh_pending', path: 'transition?status=p' },
    { id: 'S3-cancel-form', alias: 'm3_lh_paid', path: 'transition?status=c' },
];

for (const screen of SCREENS) {
    test(`A11Y ${screen.id} axe-core scan (${PHASE})`, async ({ page, orders }, testInfo) => {
        await orders.open(screen.alias, 'manager');
        if (screen.path) {
            await page.goto(page.url() + screen.path);
            await expect(page.locator('form button[type=submit]')).toBeVisible();
        }
        const results = await new AxeBuilder({ page })
            .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'])
            .analyze();

        await mkdir(outDir, { recursive: true });
        await writeFile(new URL(`axe-${screen.id}.json`, outDir), JSON.stringify(results, null, 2));
        const summary = results.violations.map(({ id, impact, nodes }) => `${impact.padEnd(8)} ${id} (${nodes.length})`);
        await testInfo.attach(`axe-${screen.id}`, { body: summary.join('\n') || 'no violations', contentType: 'text/plain' });
        console.log(`[${PHASE}] ${screen.id}: ${results.violations.length} violated rules\n  ${summary.join('\n  ')}`);

        // The screen that is fixed must have no serious or critical violations after the fix.
        if (PHASE === 'after' && screen.id === process.env.A11Y_FIXED_SCREEN) {
            expect(results.violations.filter(({ impact }) => ['serious', 'critical'].includes(impact))).toEqual([]);
        }
    });
}
