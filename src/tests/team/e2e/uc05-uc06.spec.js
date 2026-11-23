// Member 3 use cases. Specifications: sqe/use-cases/UC-05.md and sqe/use-cases/UC-06.md.
// Every test reads the order through the API before and after the action and asserts the persisted result.
import { expect, test } from './orders.js';
import { focused, tabSequence, tabTo } from './keyboard.js';
import {
    FEE_ABOVE_CAP, FEE_AT_ZERO, FEE_BELOW_CAP, FEE_BELOW_ZERO, INVALID_DATE, MSG, NEGATIVE_PAYMENT,
    ORDER_TOTAL, OVERPAYMENT, PARTIAL_PAYMENT, REMAINING_AFTER_PARTIAL,
} from './rules.js';

const confirmed = (order) => order.payments.filter(({ state }) => state === 'confirmed');
const sum = (payments) => payments.reduce((total, { amount }) => total + Number(amount), 0).toFixed(2);

/** Open the "Mark as paid" form from the order detail page and submit it. */
async function pay(page, { amount, date } = {}) {
    await page.getByRole('link', { name: /Mark as paid$/ }).click();
    await expect(page.getByRole('heading', { name: /Mark order as paid/ })).toBeVisible();
    if (amount !== undefined) await page.getByLabel('Payment amount').fill(amount);
    await page.getByLabel('Notify customer by email').uncheck();
    if (date) {
        const dateField = page.getByLabel('Payment date');
        await dateField.fill(date);
        await dateField.press('Escape');
    }
    await page.getByRole('button', { name: 'Create payment', exact: true }).click();
}

const paymentSuccess = (page) => page.getByText(MSG.paymentCreated, { exact: true });
const statusHeading = (page, status) => page.getByRole('heading', { name: new RegExp(`Order details:.*${status}`) });

// ---------------------------------------------------------------- UC-05 Settle an order through exceptional manual payments (W1)

test('UC-05 main / USA-01 partial payment then the remaining amount settles the order', async ({ page, orders }) => {
    const alias = 'm3_partial';
    const before = await orders.read(alias);
    expect(before.status).toBe('n');
    expect(confirmed(before)).toHaveLength(0);

    await orders.open(alias);
    await pay(page, { amount: PARTIAL_PAYMENT });
    await expect(paymentSuccess(page)).toBeVisible();
    await expect(statusHeading(page, 'Pending')).toBeVisible();

    const afterPartial = await orders.read(alias);
    expect(afterPartial.status).toBe('n');
    expect(confirmed(afterPartial).map(({ amount }) => amount)).toEqual([PARTIAL_PAYMENT]);

    // The form must offer exactly the outstanding balance for the second payment.
    await page.getByRole('link', { name: /Mark as paid$/ }).click();
    await expect(page.getByLabel('Payment amount')).toHaveValue(REMAINING_AFTER_PARTIAL);
    await page.getByLabel('Notify customer by email').uncheck();
    await page.getByRole('button', { name: 'Create payment', exact: true }).click();
    await expect(paymentSuccess(page)).toBeVisible();
    await expect(statusHeading(page, 'Paid')).toBeVisible();

    const after = await orders.read(alias);
    expect(after.status).toBe('p');
    expect(after.total).toBe(ORDER_TOTAL);
    expect(after.positions).toEqual(before.positions);
    expect(confirmed(after)).toHaveLength(2);
    expect(sum(confirmed(after))).toBe(ORDER_TOTAL);
});

test('UC-05 alt 1 a matching unconfirmed manual payment is reused, not duplicated', async ({ page, orders }) => {
    const alias = 'm3_reuse';
    const before = await orders.read(alias);
    expect(before.status).toBe('n');
    expect(before.payments).toEqual([expect.objectContaining({ provider: 'manual', amount: ORDER_TOTAL, state: 'created' })]);

    await orders.open(alias);
    await pay(page, { amount: ORDER_TOTAL });
    await expect(paymentSuccess(page)).toBeVisible();

    const after = await orders.read(alias);
    expect(after.status).toBe('p');
    expect(after.payments).toHaveLength(1);
    expect(after.payments[0]).toMatchObject({ id: before.payments[0].id, amount: ORDER_TOTAL, state: 'confirmed' });
});

test('UC-05 alt 2 an overpayment marks the order paid and keeps the order total', async ({ page, orders }) => {
    const alias = 'm3_overpay';
    const before = await orders.read(alias);
    expect(before.status).toBe('n');

    await orders.open(alias);
    await pay(page, { amount: OVERPAYMENT });
    await expect(paymentSuccess(page)).toBeVisible();
    await expect(statusHeading(page, 'Paid')).toBeVisible();

    const after = await orders.read(alias);
    expect(after.status).toBe('p');
    expect(after.total).toBe(ORDER_TOTAL);
    expect(confirmed(after).map(({ amount }) => amount)).toEqual([OVERPAYMENT]);
    expect(after.positions).toEqual(before.positions);
});

test('UC-05 exc 1 an invalid payment date creates no payment', async ({ page, orders }) => {
    const alias = 'm3_bad_date';
    const before = await orders.read(alias);

    await orders.open(alias);
    await pay(page, { amount: ORDER_TOTAL, date: INVALID_DATE });
    await expect(statusHeading(page, 'Pending')).toBeVisible();
    await expect(paymentSuccess(page)).toHaveCount(0);
    expect(await orders.read(alias)).toEqual(before);
});

test('UC-05 exc 1b [known defect] an invalid payment date shows an inline error', async ({ page, orders }) => {
    // Expected by usability heuristics and by the cancel form's behaviour; the payment form silently redirects
    // instead (OrderTransition.post falls through to redirect when MarkPaidForm is invalid). Remove test.fail()
    // once the defect is fixed.
    test.fail();
    await orders.open('m3_bad_date');
    await pay(page, { amount: ORDER_TOTAL, date: INVALID_DATE });
    await expect(page.getByRole('heading', { name: /Mark order as paid/ })).toBeVisible({ timeout: 3_000 });
    await expect(page.locator('.has-error')).toHaveCount(1, { timeout: 3_000 });
});

test('UC-05 exc 2 a canceled order cannot be paid', async ({ page, orders }) => {
    const alias = 'm3_canceled';
    const before = await orders.read(alias);
    expect(before.status).toBe('c');

    await orders.open(alias);
    await expect(page.getByRole('link', { name: /Mark as paid$/ })).toHaveCount(0);
    const direct = await page.request.get(page.url() + 'transition?status=p', { maxRedirects: 0 });
    expect(direct.status(), 'direct GET of the payment form for a canceled order').toBe(405);
    expect(await orders.read(alias)).toEqual(before);
});

test('UC-05 probe H2 a negative payment amount is rejected', async ({ page, orders }) => {
    const alias = 'm3_neg_amount';
    const before = await orders.read(alias);

    await orders.open(alias);
    await pay(page, { amount: NEGATIVE_PAYMENT });
    await expect(paymentSuccess(page)).toHaveCount(0);
    const after = await orders.read(alias);
    expect(confirmed(after)).toHaveLength(0);
    expect(after).toEqual(before);
});

// ---------------------------------------------------------------- UC-06 Cancel an order using only the keyboard (W2)

const CANCEL_FORM_ORDER = ['send_email', 'comment', 'No, take me back', 'Yes, cancel order'];

/** From the order detail page, reach and activate "Cancel order" with the keyboard only. */
async function openCancelFormByKeyboard(page) {
    await tabTo(page, /Cancel order$/);
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Cancel order', exact: true })).toBeVisible();
}

/** Tab into the fee field and type a value, replacing any existing text. */
async function typeFee(page, value) {
    await tabTo(page, 'cancellation_fee');
    await page.keyboard.press('Control+A');
    await page.keyboard.type(value);
}

test('UC-06 main paid order canceled without a fee using only the keyboard', async ({ page, orders }) => {
    const alias = 'm3_kbd_paid';
    const before = await orders.read(alias);
    expect(before.status).toBe('p');

    await orders.open(alias);
    await openCancelFormByKeyboard(page);

    // Focus order: fee field first, then the remaining controls in reading order ending on the submit button.
    await tabTo(page, 'cancellation_fee');
    expect(await tabSequence(page, CANCEL_FORM_ORDER.length)).toEqual(CANCEL_FORM_ORDER);

    // Untick e-mail with Space, then submit with Enter on the focused submit button.
    await tabTo(page, 'send_email', { backwards: true });
    await page.keyboard.press('Space');
    await expect(page.getByLabel('Notify customer by email')).not.toBeChecked();
    await tabTo(page, 'Yes, cancel order');
    await page.keyboard.press('Enter');
    await expect(page.locator('.alert-success').filter({ hasText: MSG.canceled })).toBeVisible();

    const after = await orders.read(alias);
    expect(after).toEqual({ ...before, status: 'c', cancellationDate: expect.any(String) });
    expect(after.fees).toHaveLength(0);
    expect(confirmed(after)).toEqual(confirmed(before));
});

test('UC-06 alt 1 pending order canceled with a zero fee', async ({ page, orders }) => {
    const alias = 'm3_zero_fee';
    const before = await orders.read(alias);
    expect(before.status).toBe('n');

    await orders.open(alias);
    await openCancelFormByKeyboard(page);
    await page.getByLabel('Notify customer by email').uncheck();
    await typeFee(page, FEE_AT_ZERO);
    await page.keyboard.press('Enter');
    await expect(page.locator('.alert-success').filter({ hasText: MSG.canceled })).toBeVisible();

    const after = await orders.read(alias);
    expect(after).toEqual({ ...before, status: 'c', cancellationDate: expect.any(String) });
    expect(after.fees).toHaveLength(0);
});

test('UC-06 alt 2 manager abandons the cancellation with "No, take me back"', async ({ page, orders }) => {
    const alias = 'm3_abandon';
    const before = await orders.read(alias);

    await orders.open(alias);
    const orderUrl = page.url();
    await openCancelFormByKeyboard(page);
    await tabTo(page, 'No, take me back');
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(orderUrl);
    await expect(statusHeading(page, 'Paid')).toBeVisible();
    expect(await orders.read(alias)).toEqual(before);
});

test('UC-06 exc 1 / USA-02 fee above the total is explained, corrected and accepted by keyboard', async ({ page, orders }) => {
    const alias = 'm3_fee_fix';
    const before = await orders.read(alias);
    expect(before.status).toBe('p');

    await orders.open(alias);
    await openCancelFormByKeyboard(page);
    await tabTo(page, 'cancellation_fee');
    expect(await tabSequence(page, CANCEL_FORM_ORDER.length)).toEqual(CANCEL_FORM_ORDER);
    await tabTo(page, 'send_email', { backwards: true });
    await page.keyboard.press('Space');

    // 1. Submit a value the business rule rejects.
    await typeFee(page, FEE_ABOVE_CAP);
    await page.keyboard.press('Enter');

    // 2. The error must explain what to correct, next to the field, and keep the typed value.
    await expect(page.getByText(MSG.feeAboveTotal)).toBeVisible();
    const feeField = page.getByLabel('Keep a cancellation fee of');
    await expect(feeField).toHaveValue(FEE_ABOVE_CAP);
    await expect(page.locator('.form-group.has-error')).toContainText(MSG.feeAboveTotal);
    expect(await orders.read(alias)).toEqual(before);

    // 3. Correct the value and submit with the keyboard.
    await feeField.focus();
    expect(await focused(page)).toBe('cancellation_fee');
    await page.keyboard.press('Control+A');
    await page.keyboard.type(FEE_BELOW_CAP);
    await page.keyboard.press('Enter');
    await expect(page.locator('.alert-success').filter({ hasText: MSG.canceled })).toBeVisible();

    // A retained fee within the total: positions canceled, total reduced to the fee, still paid (20.00 >= 19.99).
    const after = await orders.read(alias);
    expect(after.status).toBe('p');
    expect(after.total).toBe(FEE_BELOW_CAP);
    expect(after.positions.every(({ canceled }) => canceled)).toBe(true);
    expect(after.fees).toEqual([{ type: 'cancellation', value: FEE_BELOW_CAP }]);
    expect(confirmed(after)).toEqual(confirmed(before));
});

test('UC-06 exc 2 a negative cancellation fee is rejected (BVA just below zero)', async ({ page, orders }) => {
    const alias = 'm3_neg_fee';
    const before = await orders.read(alias);
    expect(before.status).toBe('p');

    await orders.open(alias);
    await openCancelFormByKeyboard(page);
    await page.getByLabel('Notify customer by email').uncheck();
    await typeFee(page, FEE_BELOW_ZERO);
    await page.keyboard.press('Enter');

    await expect(page.locator('.form-group.has-error')).toBeVisible();
    await expect(page.locator('.alert-success')).toHaveCount(0);
    expect(await orders.read(alias)).toEqual(before);
});
