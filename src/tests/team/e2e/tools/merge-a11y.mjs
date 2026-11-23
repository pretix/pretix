// Merge axe-core and Lighthouse accessibility findings and count an issue found by both tools once.
//
// Lighthouse's accessibility audits are axe-core rules, so both tools use the same rule id, but they print
// different CSS selectors for the same element. An issue is therefore keyed on
//   (screen, rule id, normalised opening HTML tag of the element, occurrence number)
// where the occurrence number separates several identical-looking elements (e.g. three `<a class="arrow">`).
//
// Usage (from src/tests/team/e2e):  node tools/merge-a11y.mjs before
// Output: local/sqe/evidence/a11y/<phase>/merged-findings.{json,md}
import { readFile, readdir, writeFile } from 'node:fs/promises';

const PHASE = process.argv[2] || 'before';
const root = new URL('../../../../../', import.meta.url);
const axeDir = new URL(`local/sqe/evidence/a11y/${PHASE}/`, root);
const lhDir = new URL(`local/sqe/evidence/lighthouse/${PHASE}/`, root);

/**
 * Opening tag with whitespace collapsed and attributes sorted, so both tools' snippets compare equal.
 * Lighthouse truncates long attribute values with an ellipsis, so values are compared on their first 40 chars.
 */
function openingTag(html = '') {
    const tag = (html.match(/^<[^>]*>/) || [html])[0].replace(/\s+/g, ' ').trim();
    const name = (tag.match(/^<\s*([a-zA-Z0-9-]+)/) || [])[1] || tag;
    const attrs = [...tag.matchAll(/([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:="([^"]*)")?/g)].slice(1)
        .map(([, k, v = '']) => `${k}=${v.replace(/…$/, '').slice(0, 40)}`).sort();
    return `<${name.toLowerCase()} ${attrs.join(' ')}>`;
}

const findings = new Map();
const impactByRule = {};

function addAll(tool, screen, rule, nodes, data) {
    const seen = {};
    for (const node of nodes) {
        const tag = openingTag(node.html);
        seen[tag] = (seen[tag] || 0) + 1;
        const key = `${screen}|${rule}|${tag}|${seen[tag]}`;
        const entry = findings.get(key) || { screen, rule, element: node.selector, html: node.html.slice(0, 140), tools: new Set() };
        entry.tools.add(tool);
        for (const [k, v] of Object.entries(data)) if (!entry[k] && v) entry[k] = v;
        findings.set(key, entry);
    }
}

for (const file of (await readdir(axeDir)).filter((f) => /^axe-.*\.json$/.test(f))) {
    const screen = file.slice(4, -5);
    const result = JSON.parse(await readFile(new URL(file, axeDir), 'utf8'));
    for (const v of result.violations) {
        impactByRule[v.id] = v.impact;
        addAll('axe', screen, v.id, v.nodes.map((n) => ({ selector: n.target.join(' '), html: n.html })), {
            impact: v.impact, help: v.help, wcag: v.tags.filter((t) => /^wcag\d/.test(t)).join(' '),
        });
    }
}

const pageLevel = [];
let lighthouseFiles = [];
try { lighthouseFiles = (await readdir(lhDir)).filter((f) => /-run1\.json$/.test(f)); } catch { /* not run yet */ }
for (const file of lighthouseFiles) {
    const screen = file.replace(/-run1\.json$/, '');
    const lhr = JSON.parse(await readFile(new URL(file, lhDir), 'utf8'));
    for (const { id } of lhr.categories.accessibility.auditRefs) {
        const audit = lhr.audits[id];
        if (audit.score !== 0 || audit.scoreDisplayMode !== 'binary') continue;
        const nodes = (audit.details?.items || []).map((item) => ({
            selector: item.node?.selector || '(page)', html: item.node?.snippet || '',
        }));
        addAll('lighthouse', screen, id, nodes, { help: audit.title });
    }
    // Best-practices and SEO failures are page-level and have no axe counterpart: reported separately.
    for (const cat of ['best-practices', 'seo']) {
        for (const { id } of lhr.categories[cat].auditRefs) {
            const audit = lhr.audits[id];
            if (audit.score === 0 && audit.scoreDisplayMode === 'binary') pageLevel.push({ screen, category: cat, rule: id, help: audit.title });
        }
    }
}

const order = { critical: 0, serious: 1, moderate: 2, minor: 3, undefined: 4 };
const rows = [...findings.values()]
    .map((f) => ({ ...f, impact: f.impact || impactByRule[f.rule], tools: [...f.tools].sort().join('+') }))
    .sort((a, b) => order[a.impact] - order[b.impact] || a.rule.localeCompare(b.rule) || a.screen.localeCompare(b.screen));

const byRule = {};
for (const r of rows) {
    byRule[r.rule] ??= { rule: r.rule, impact: r.impact, wcag: r.wcag, help: r.help, count: 0, screens: new Set(), both: 0 };
    byRule[r.rule].count++;
    byRule[r.rule].screens.add(r.screen.split('-')[0]);
    if (r.tools === 'axe+lighthouse') byRule[r.rule].both++;
}

await writeFile(new URL('merged-findings.json', axeDir), JSON.stringify({ phase: PHASE, issues: rows, pageLevel }, null, 2));
const esc = (s = '') => String(s).replace(/\|/g, '\\|').replace(/\n/g, ' ');
const md = [
    `# Accessibility findings (${PHASE})`, '',
    `${rows.length} unique element-level issues across ${new Set(rows.map((r) => r.screen)).size} screens; `
        + `${rows.filter((r) => r.tools === 'axe+lighthouse').length} were found by both tools and are counted once.`, '',
    '## By rule', '',
    '| Rule | Impact | WCAG | Issues | Found by both | Screens | Problem |', '|---|---|---|---|---|---|---|',
    ...Object.values(byRule).map((r) => `| ${r.rule} | ${r.impact || '-'} | ${r.wcag || '-'} | ${r.count} | ${r.both} | ${[...r.screens].join(', ')} | ${esc(r.help)} |`),
    '', '## Every issue', '',
    '| # | Screen | Rule | Impact | Element | Found by |', '|---|---|---|---|---|---|',
    ...rows.map((r, i) => `| ${i + 1} | ${r.screen} | ${r.rule} | ${r.impact || '-'} | \`${esc(r.element)}\` | ${r.tools} |`),
    '', '## Page-level Lighthouse audits (best practices, SEO)', '',
    '| Screen | Category | Audit | Problem |', '|---|---|---|---|',
    ...pageLevel.map((p) => `| ${p.screen} | ${p.category} | ${p.rule} | ${esc(p.help)} |`),
].join('\n');
await writeFile(new URL('merged-findings.md', axeDir), md + '\n');
console.log(md.split('\n## Every issue')[0]);
