// Merge axe-core and Lighthouse accessibility findings and count an issue found by both tools once.
// Lighthouse's accessibility audits are axe-core rules, so both use the same rule id; an issue is the pair
// (screen, rule id, CSS selector of the element).
//
// Usage (from src/tests/team/e2e):  node tools/merge-a11y.mjs before
// Output: local/sqe/evidence/a11y/<phase>/merged-findings.{json,md}
import { readFile, readdir, writeFile } from 'node:fs/promises';

const PHASE = process.argv[2] || 'before';
const root = new URL('../../../../../', import.meta.url);
const axeDir = new URL(`local/sqe/evidence/a11y/${PHASE}/`, root);
const lhDir = new URL(`local/sqe/evidence/lighthouse/${PHASE}/`, root);

const findings = new Map();
const add = (screen, rule, selector, data, tool) => {
    const key = `${screen}|${rule}|${selector}`;
    const existing = findings.get(key) || { screen, rule, selector, tools: new Set(), ...data };
    existing.tools.add(tool);
    for (const [k, v] of Object.entries(data)) if (!existing[k] && v) existing[k] = v;
    findings.set(key, existing);
};

for (const file of (await readdir(axeDir)).filter((f) => /^axe-.*\.json$/.test(f))) {
    const screen = file.slice(4, -5);
    const result = JSON.parse(await readFile(new URL(file, axeDir), 'utf8'));
    for (const v of result.violations) {
        for (const node of v.nodes) {
            add(screen, v.id, node.target.join(' '), {
                impact: v.impact, help: v.help, wcag: v.tags.filter((t) => /^wcag\d/.test(t)).join(' '),
                html: node.html.slice(0, 160), failure: (node.failureSummary || '').replace(/\s+/g, ' '),
            }, 'axe');
        }
    }
}

let lighthouseFiles = [];
try { lighthouseFiles = (await readdir(lhDir)).filter((f) => /-run1\.json$/.test(f)); } catch { /* not run yet */ }
for (const file of lighthouseFiles) {
    const screen = file.replace(/-run1\.json$/, '');
    const lhr = JSON.parse(await readFile(new URL(file, lhDir), 'utf8'));
    const refs = lhr.categories.accessibility.auditRefs.map(({ id }) => id);
    for (const id of refs) {
        const audit = lhr.audits[id];
        if (audit.score !== 0 || audit.scoreDisplayMode !== 'binary') continue;
        for (const item of audit.details?.items || []) {
            const selector = item.node?.selector || '(page)';
            add(screen, id, selector, { help: audit.title, html: (item.node?.snippet || '').slice(0, 160) }, 'lighthouse');
        }
    }
    // Best-practices and SEO failures are reported per screen, not merged with axe (different rule sets).
    for (const cat of ['best-practices', 'seo']) {
        for (const { id } of lhr.categories[cat].auditRefs) {
            const audit = lhr.audits[id];
            if (audit.score === 0 && audit.scoreDisplayMode === 'binary') {
                add(screen, `${cat}:${id}`, '(page)', { help: audit.title }, 'lighthouse');
            }
        }
    }
}

const order = { critical: 0, serious: 1, moderate: 2, minor: 3, undefined: 4 };
const rows = [...findings.values()]
    .map((f) => ({ ...f, tools: [...f.tools].sort().join('+') }))
    .sort((a, b) => order[a.impact] - order[b.impact] || a.screen.localeCompare(b.screen) || a.rule.localeCompare(b.rule));

await writeFile(new URL('merged-findings.json', axeDir), JSON.stringify(rows, null, 2));
const esc = (s = '') => String(s).replace(/\|/g, '\\|').replace(/\n/g, ' ');
const md = [
    `# Accessibility findings (${PHASE})`, '',
    `${rows.length} unique issues; ${rows.filter((r) => r.tools === 'axe+lighthouse').length} found by both tools (counted once).`, '',
    '| # | Screen | Rule | Impact | WCAG | Element | Found by | Problem |',
    '|---|---|---|---|---|---|---|---|',
    ...rows.map((r, i) => `| ${i + 1} | ${r.screen} | ${r.rule} | ${r.impact || '-'} | ${r.wcag || '-'} | \`${esc(r.selector)}\` | ${r.tools} | ${esc(r.help)} |`),
].join('\n');
await writeFile(new URL('merged-findings.md', axeDir), md + '\n');
console.log(md);
