import { expect, test } from './orders.js';

const confirmed = (order) => order.payments.filter(({ state }) => state === 'confirmed');

async function pay(page, { amount = '20.00', date } = {}) {
    await page.getByRole('link', { name: /Mark as paid$/ }).click();
    await page.getByLabel('Payment amount').fill(amount);
    await page.getByLabel('Notify customer by email').uncheck();
    if (date) {
        const dateField = page.getByLabel('Payment date');
        await dateField.fill(date);
        await dateField.press('Escape');
    }
    await page.getByRole('button', { name: 'Create payment', exact: true }).click();
}

const successfulPayments = [
    { name: 'main pending order', alias: 'pay_pending', initial: 'n' },
    { name: 'alternative prior payment date', alias: 'pay_prior_date', initial: 'n', priorDate: true },
    { name: 'alternative expired order with quota', alias: 'pay_expired', initial: 'e' },
];

for (const { name, alias, initial, priorDate } of successfulPayments) {
    test('UC-01 ' + name, async ({ page, orders }) => {
        const before = await orders.read(alias);
        expect(before.status).toBe(initial);
        expect(confirmed(before)).toHaveLength(0);
        await orders.open(alias);
        await pay(page, { date: priorDate ? orders.priorPaymentDate : undefined });
        await expect(page.getByText('The payment has been created successfully.', { exact: true })).toBeVisible();

        const after = await orders.read(alias);
        expect(after.status).toBe('p');
        expect(after.total).toBe('20.00');
        expect(after.positions).toEqual(before.positions);
        const payments = confirmed(after);
        expect(payments).toHaveLength(1);
        expect(payments[0]).toMatchObject({ provider: 'manual', amount: '20.00' });
        if (priorDate) expect(payments[0].date.slice(0, 10)).toBe(orders.priorPaymentDate);
    });
}

test('UC-01 exception excessive decimal precision', async ({ page, orders }) => {
    const alias = 'pay_precision';
    const before = await orders.read(alias);
    await orders.open(alias);
    await pay(page, { amount: '20.001' });
    await expect(page.getByRole('heading', { name: /Order details:.*Pending/ })).toBeVisible();
    await expect(page.getByText('The payment has been created successfully.', { exact: true })).toHaveCount(0);
    expect(await orders.read(alias)).toEqual(before);
});

test('UC-01 exception expired order with exhausted quota', async ({ page, orders }) => {
    const alias = 'pay_quota_blocked';
    const before = await orders.read(alias);
    expect(before.status).toBe('e');
    await orders.open(alias);
    await pay(page);
    await expect(page.getByText(/Limited ticket.*no longer available/)).toBeVisible();

    const after = await orders.read(alias);
    expect(after.status).toBe('e');
    expect(after.total).toBe(before.total);
    expect(after.positions).toEqual(before.positions);
    expect(confirmed(after)).toEqual(confirmed(before));
    expect(after.payments).toEqual([expect.objectContaining({ state: 'failed' })]);
});

const cancellationCases = [
    { name: 'main paid order without a fee', alias: 'cancel_paid', initial: 'p' },
    { name: 'alternative pending order without a fee', alias: 'cancel_pending', initial: 'n' },
    { name: 'alternative expired order without a fee', alias: 'cancel_expired', initial: 'e' },
];

for (const { name, alias, initial } of cancellationCases) {
    test('UC-02 ' + name, async ({ page, orders }) => {
        const before = await orders.read(alias);
        expect(before.status).toBe(initial);
        await orders.open(alias);
        await page.getByRole('link', { name: /Cancel order$/ }).click();
        await page.getByLabel('Notify customer by email').uncheck();
        await page.getByRole('button', { name: 'Yes, cancel order', exact: true }).click();
        await expect(page.locator('.alert-success').filter({ hasText: 'The order has been canceled.' })).toBeVisible();

        const after = await orders.read(alias);
        expect(after).toEqual({ ...before, status: 'c', cancellationDate: expect.any(String) });
    });
}

const deniedCancellations = [
    { name: 'viewer can read but cannot cancel', alias: 'cancel_viewer', role: 'viewer' },
    { name: 'already-canceled order has no cancellation action', alias: 'cancel_canceled', role: 'manager' },
];

for (const { name, alias, role } of deniedCancellations) {
    test('UC-02 exception ' + name, async ({ page, orders }) => {
        const before = await orders.read(alias);
        await orders.open(alias, role);
        await expect(page.getByRole('link', { name: /Cancel order$/ })).toHaveCount(0);
        expect(await orders.read(alias)).toEqual(before);
    });
}
