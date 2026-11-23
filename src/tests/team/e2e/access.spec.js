// Member 3 defensive security: access matrix (AC-xx) and control checks (SEC-Cx).
// Every decision records role, action, expected, observed and evidence to local/sqe/evidence/access-matrix.jsonl
// and as a Playwright attachment. Hiding a link is not access control, so denied actions are sent directly.
import { appendFile, mkdir, readFile } from 'node:fs/promises';
import { expect, test } from './orders.js';
import { ORDER_TOTAL } from './rules.js';

const fixtureFile = new URL('../../../../local/sqe/windows/fixtures.json', import.meta.url);
const evidenceDir = new URL('../../../../local/sqe/evidence/', import.meta.url);
const fixtures = JSON.parse(await readFile(fixtureFile, 'utf8'));
const controlOrder = (code) => `/control/event/${fixtures.organizer}/${fixtures.event}/orders/${code}/`;
const apiOrder = (code) => `/api/v1/organizers/${fixtures.organizer}/events/${fixtures.event}/orders/${code}/`;
const token = (role) => ({ Authorization: 'Token ' + fixtures.roles[role].token });
const today = () => new Date().toISOString().slice(0, 10);

async function record(testInfo, decision) {
    const entry = { ...decision, pass: decision.expected === decision.observed, at: new Date().toISOString() };
    await testInfo.attach('access-decision', { body: JSON.stringify(entry, null, 2), contentType: 'application/json' });
    await mkdir(evidenceDir, { recursive: true });
    await appendFile(new URL('access-matrix.jsonl', evidenceDir), JSON.stringify(entry) + '\n');
    expect(decision.observed, `${decision.id} ${decision.role} ${decision.action}`).toBe(decision.expected);
}

/** CSRF token for the logged-in browser session (Django sends it as a cookie). */
async function csrf(page) {
    const cookie = (await page.context().cookies()).find(({ name }) => name.endsWith('pretix_csrftoken'));
    expect(cookie, 'CSRF cookie after login').toBeTruthy();
    return cookie.value;
}

async function postTransition(page, code, form, { withCsrf = true } = {}) {
    const url = new URL(controlOrder(code) + 'transition', page.url()).href;
    const headers = { Referer: url };
    if (withCsrf) headers['X-CSRFToken'] = await csrf(page);
    return page.request.post(url, { form, headers, maxRedirects: 0 });
}

/** Page title of an HTML response and whether it is the CSRF failure page (pretix csrffail.html, title "Verification failed"). */
async function describe(response) {
    const text = await response.text();
    const title = (text.match(/<title>([\s\S]*?)<\/title>/i) || [])[1]?.replace(/\s+/g, ' ').trim() || '';
    return { title, csrfFailurePage: /Verification failed/.test(title) };
}

const PAY_FORM = { status: 'p', amount: ORDER_TOTAL, payment_date: today() };
const CANCEL_FORM = { status: 'c', cancellation_fee: '' };

// ---------------------------------------------------------------- allowed actions

test('AC-01 manager may record a payment (UI POST)', async ({ page, orders }, testInfo) => {
    const alias = 'm3_sec_mgr_pay';
    await orders.open(alias, 'manager');
    const response = await postTransition(page, fixtures.orders[alias], PAY_FORM);
    const after = await orders.read(alias);
    await record(testInfo, {
        id: 'AC-01', role: 'manager', action: 'POST transition status=p', expected: 'allowed',
        observed: response.status() === 302 && after.status === 'p' ? 'allowed' : 'denied',
        evidence: { http: response.status(), statusAfter: after.status },
    });
});

test('AC-02 manager may cancel an order (UI POST)', async ({ page, orders }, testInfo) => {
    const alias = 'm3_sec_mgr_cancel';
    await orders.open(alias, 'manager');
    const response = await postTransition(page, fixtures.orders[alias], CANCEL_FORM);
    const after = await orders.read(alias);
    await record(testInfo, {
        id: 'AC-02', role: 'manager', action: 'POST transition status=c', expected: 'allowed',
        observed: response.status() === 302 && after.status === 'c' ? 'allowed' : 'denied',
        evidence: { http: response.status(), statusAfter: after.status },
    });
});

test('AC-03 viewer may read the order detail page', async ({ page, orders }, testInfo) => {
    const alias = 'm3_sec_pay';
    await orders.open(alias, 'viewer'); // asserts the order heading is visible
    const response = await page.request.get(controlOrder(fixtures.orders[alias]));
    await record(testInfo, {
        id: 'AC-03', role: 'viewer', action: 'GET order detail', expected: 'allowed',
        observed: response.status() === 200 ? 'allowed' : 'denied', evidence: { http: response.status() },
    });
});

test('AC-08 viewer may read the order through the API', async ({ request }, testInfo) => {
    const response = await request.get(apiOrder(fixtures.orders.m3_sec_api_pay), { headers: token('viewer') });
    await record(testInfo, {
        id: 'AC-08', role: 'viewer', action: 'API GET order', expected: 'allowed',
        observed: response.status() === 200 ? 'allowed' : 'denied', evidence: { http: response.status() },
    });
});

// ---------------------------------------------------------------- denied actions (sent directly, state must not change)

const viewerUiDenials = [
    { id: 'AC-04', alias: 'm3_sec_pay', action: 'GET payment form directly', method: 'get', query: '?status=p' },
    { id: 'AC-05', alias: 'm3_sec_pay', action: 'POST payment with valid CSRF', method: 'post', form: PAY_FORM },
    { id: 'AC-06', alias: 'm3_sec_cancel', action: 'GET cancel form directly', method: 'get', query: '?status=c' },
    { id: 'AC-07', alias: 'm3_sec_cancel', action: 'POST cancel with valid CSRF', method: 'post', form: CANCEL_FORM },
];

for (const { id, alias, action, method, query, form } of viewerUiDenials) {
    test(`${id} viewer is denied: ${action}`, async ({ page, orders }, testInfo) => {
        const before = await orders.read(alias);
        await orders.open(alias, 'viewer');
        const code = fixtures.orders[alias];
        const response = method === 'get'
            ? await page.request.get(controlOrder(code) + 'transition' + query, { maxRedirects: 0 })
            : await postTransition(page, code, form);
        const after = await orders.read(alias);
        const page403 = await describe(response);
        await record(testInfo, {
            id, role: 'viewer', action, expected: 'denied',
            observed: response.status() === 403 && JSON.stringify(after) === JSON.stringify(before) ? 'denied' : 'allowed',
            evidence: { http: response.status(), ...page403, statusBefore: before.status, statusAfter: after.status },
        });
        // The denial must come from the role check, not from CSRF protection (the token sent is valid).
        expect(page403.csrfFailurePage, `${id} 403 must come from the role check, not CSRF`).toBe(false);
    });
}

const viewerApiDenials = [
    { id: 'AC-09', alias: 'm3_sec_api_pay', endpoint: 'mark_paid/' },
    { id: 'AC-10', alias: 'm3_sec_api_cancel', endpoint: 'mark_canceled/' },
];

for (const { id, alias, endpoint } of viewerApiDenials) {
    test(`${id} viewer is denied: API POST ${endpoint}`, async ({ request, orders }, testInfo) => {
        const before = await orders.read(alias);
        const response = await request.post(apiOrder(fixtures.orders[alias]) + endpoint, {
            headers: token('viewer'), data: { send_email: false },
        });
        const after = await orders.read(alias);
        await record(testInfo, {
            id, role: 'viewer', action: `API POST ${endpoint}`, expected: 'denied',
            observed: response.status() === 403 && JSON.stringify(after) === JSON.stringify(before) ? 'denied' : 'allowed',
            evidence: { http: response.status(), body: (await response.text()).slice(0, 200), statusAfter: after.status },
        });
    });
}

test('AC-11 anonymous visitor is sent to the login page', async ({ browser }, testInfo) => {
    const context = await browser.newContext();
    const response = await context.request.get(controlOrder(fixtures.orders.m3_sec_pay), { maxRedirects: 0 });
    const location = response.headers().location || '';
    await context.close();
    await record(testInfo, {
        id: 'AC-11', role: 'anonymous', action: 'GET order detail', expected: 'denied',
        observed: response.status() === 302 && location.includes('/control/login') ? 'denied' : 'allowed',
        evidence: { http: response.status(), location },
    });
});

test('AC-12 anonymous API client receives 401', async ({ request }, testInfo) => {
    const response = await request.get(apiOrder(fixtures.orders.m3_sec_api_pay));
    await record(testInfo, {
        id: 'AC-12', role: 'anonymous', action: 'API GET order', expected: 'denied',
        observed: response.status() === 401 ? 'denied' : 'allowed', evidence: { http: response.status() },
    });
});

// ---------------------------------------------------------------- control checks

test('SEC-C3 state-changing POST without a CSRF token is rejected', async ({ page, orders }, testInfo) => {
    const alias = 'm3_sec_mgr_pay';
    await orders.open(alias, 'manager');
    const before = await orders.read(alias);
    const response = await postTransition(page, fixtures.orders[alias], CANCEL_FORM, { withCsrf: false });
    const after = await orders.read(alias);
    const page403 = await describe(response);
    await record(testInfo, {
        id: 'SEC-C3', role: 'manager', action: 'POST cancel without CSRF token', expected: 'denied',
        observed: response.status() === 403 && JSON.stringify(after) === JSON.stringify(before) ? 'denied' : 'allowed',
        evidence: { http: response.status(), ...page403, statusAfter: after.status },
    });
    expect(page403.csrfFailurePage, 'the 403 must come from CSRF protection').toBe(true);
});

test('SEC-C1 session cookie attributes on the http test instance', async ({ page, orders }, testInfo) => {
    await orders.open('m3_sec_pay', 'viewer');
    const cookies = await page.context().cookies();
    const session = cookies.find(({ name }) => name.endsWith('pretix_session'));
    const csrfCookie = cookies.find(({ name }) => name.endsWith('pretix_csrftoken'));
    const observation = {
        session: session && { name: session.name, httpOnly: session.httpOnly, secure: session.secure, sameSite: session.sameSite },
        csrf: csrfCookie && { name: csrfCookie.name, httpOnly: csrfCookie.httpOnly, secure: csrfCookie.secure, sameSite: csrfCookie.sameSite },
    };
    await testInfo.attach('cookie-attributes', { body: JSON.stringify(observation, null, 2), contentType: 'application/json' });
    await mkdir(evidenceDir, { recursive: true });
    await appendFile(new URL('cookie-attributes.json', evidenceDir), JSON.stringify(observation) + '\n');
    // HttpOnly is unconditional in settings.py; Secure/__Host-/SameSite=None depend on https (multidomain/middlewares.py).
    expect(session.httpOnly).toBe(true);
    expect(session.secure).toBe(false);
});
