// Member 3 use cases. Specifications: sqe/use-cases/UC-05.md and sqe/use-cases/UC-06.md.
// Every test reads the order through the API before and after the action and asserts the persisted result.
import { expect, test } from './orders.js';
import { focused, tabSequence, tabTo } from './keyboard.js';
import {
    EMPTY_DATE, FEE_ABOVE_CAP, FEE_AT_ZERO, FEE_BELOW_CAP, FEE_BELOW_ZERO, MSG, NEGATIVE_PAYMENT, NON_NUMERIC_AMOUNT,
    ORDER_TOTAL, OVERPAYMENT, PARTIAL_PAYMENT, REMAINING_AFTER_PARTIAL, UNPARSEABLE_DATE,
} from './rules.js';

/** Attach the persisted order as evidence, so a known-defect test shows exactly what was stored. */
async function attachState(testInfo, label, order) {
    await testInfo.attach(label, { body: JSON.stringify(order, null, 2), contentType: 'application/json' });
}

const confirmed = (order) => order.payments.filter(({ state }) => state === 'confirmed');
const sum = (payments) => payments.reduce((total, { amount }) => total + Number(amount), 0).toFixed(2);

/**
 * Perform a submitting action and wait until the server has answered the POST and the next page has loaded.
 * Without this, an API read-back can race ahead of the submission and see the old state.
 */
async function submitAndWait(page, action) {
    const [response] = await Promise.all([
        page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/transition')),
        action(),
    ]);
    await page.waitForLoadState('load');
    return response;
}

/** Open the "Mark as paid" form from the order detail page and submit it. */
async function pay(page, { amount, date, expectPost = true } = {}) {
    await page.getByRole('link', { name: /Mark as paid$/ }).click();
    await expect(page.getByRole('heading', { name: /Mark order as paid/ })).toBeVisible();
    if (amount !== undefined) await page.getByLabel('Payment amount').fill(amount);
    await page.getByLabel('Notify customer by email').uncheck();
    if (date !== undefined) {
        const dateField = page.getByLabel('Payment date');
        await dateField.fill(date);
        await dateField.press('Escape');
        await expect(dateField, 'date actually submitted').toHaveValue(date);
    }
    const submit = () => page.getByRole('button', { name: 'Create payment', exact: true }).click();
    if (expectPost) await submitAndWait(page, submit);
    else await submit();
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
    await submitAndWait(page, () => page.getByRole('button', { name: 'Create payment', exact: true }).click());
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

test('UC-05 exc 1 a missing payment date is blocked before submission and explained', async ({ page, orders }) => {
    const alias = 'm3_bad_date';
    const before = await orders.read(alias);

    await orders.open(alias);
    const posts = [];
    page.on('request', (request) => { if (request.method() === 'POST') posts.push(request.url()); });
    await pay(page, { amount: ORDER_TOTAL, date: EMPTY_DATE, expectPost: false });

    // The required field is validated by the browser: the form stays open with a message and nothing is sent.
    await expect(page.getByRole('heading', { name: /Mark order as paid/ })).toBeVisible();
    const validity = await page.getByLabel('Payment date').evaluate((el) => ({ valid: el.validity.valid, message: el.validationMessage }));
    expect(validity.valid).toBe(false);
    expect(validity.message).not.toBe('');
    expect(posts).toEqual([]);
    expect(await orders.read(alias)).toEqual(before);
});

test('UC-05 exc 1b a non-numeric payment amount creates no payment', async ({ page, orders }) => {
    const alias = 'm3_bad_date';
    const before = await orders.read(alias);

    await orders.open(alias);
    await pay(page, { amount: NON_NUMERIC_AMOUNT });
    await expect(paymentSuccess(page)).toHaveCount(0);
    expect(await orders.read(alias)).toEqual(before);
});

test('UC-05 exc 1c [known defect D-03] a non-numeric payment amount shows an inline error', async ({ page, orders }) => {
    // Expected by usability heuristics and by the cancel form's behaviour; the payment form silently redirects to
    // the order instead (OrderTransition.post falls through to redirect when MarkPaidForm is invalid). Remove
    // test.fail() once D-03 is fixed.
    test.fail();
    await orders.open('m3_bad_date');
    await pay(page, { amount: NON_NUMERIC_AMOUNT });
    await expect(page.getByRole('heading', { name: /Mark order as paid/ })).toBeVisible({ timeout: 3_000 });
    await expect(page.locator('.form-group.has-error')).toContainText(/number/i, { timeout: 3_000 });
});

test('UC-05 observation U-01 the date picker silently replaces an unparseable date', async ({ page, orders }) => {
    // Read-only: the form is opened but not submitted. Documents why an invalid typed date never reaches the
    // server: the client-side picker restores the last valid date (today) without telling the user.
    await orders.open('m3_bad_date');
    await page.getByRole('link', { name: /Mark as paid$/ }).click();
    const dateField = page.getByLabel('Payment date');
    const initial = await dateField.inputValue();
    await dateField.fill(UNPARSEABLE_DATE);
    await expect(dateField).toHaveValue(UNPARSEABLE_DATE);
    await dateField.press('Escape');
    await expect(dateField).toHaveValue(initial);
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

test('UC-05 probe H2 [known defect D-02] a negative payment amount is rejected', async ({ page, orders }, testInfo) => {
    // Observed on the baseline: a confirmed manual payment of -0.01 is stored (MarkPaidForm.amount has no
    // minimum). The assertions state the business rule; test.fail() keeps the suite green while D-02 is open.
    test.fail();
    const alias = 'm3_neg_amount';
    const before = await orders.read(alias);

    await orders.open(alias);
    await pay(page, { amount: NEGATIVE_PAYMENT });
    const after = await orders.read(alias);
    await attachState(testInfo, 'persisted-after', after);
    expect(confirmed(after), 'no confirmed payment may be stored').toHaveLength(0);
    expect(after).toEqual(before);
    await expect(paymentSuccess(page)).toHaveCount(0);
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

/** Untick "Notify customer by email" with Tab + Space only. */
async function untickEmailByKeyboard(page) {
    await tabTo(page, 'send_email');
    await page.keyboard.press('Space');
    await expect(page.getByLabel('Notify customer by email')).not.toBeChecked();
}

/** Submit the focused form with Enter and wait for the server's answer before anything is read back. */
const enterAndWait = (page) => submitAndWait(page, () => page.keyboard.press('Enter'));

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
    await enterAndWait(page);
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
    await untickEmailByKeyboard(page);
    await typeFee(page, FEE_AT_ZERO);
    await enterAndWait(page);
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
    await enterAndWait(page);

    // 2. The error must explain what to correct, next to the field, and keep the typed value.
    await expect(page.getByText(MSG.feeAboveTotal)).toBeVisible();
    const feeField = page.getByLabel('Keep a cancellation fee of');
    await expect(feeField).toHaveValue(FEE_ABOVE_CAP);
    await expect(page.locator('.form-group.has-error')).toContainText(MSG.feeAboveTotal);
    expect(await orders.read(alias)).toEqual(before);

    // 3. Correct the value and submit with the keyboard (Tab back into the fee field from the top of the page).
    await tabTo(page, 'cancellation_fee');
    expect(await focused(page)).toBe('cancellation_fee');
    await page.keyboard.press('Control+A');
    await page.keyboard.type(FEE_BELOW_CAP);
    await enterAndWait(page);
    await expect(page.locator('.alert-success').filter({ hasText: MSG.canceled })).toBeVisible();

    // A retained fee within the total: positions canceled, total reduced to the fee, still paid (20.00 >= 19.99).
    const after = await orders.read(alias);
    expect(after.status).toBe('p');
    expect(after.total).toBe(FEE_BELOW_CAP);
    expect(after.positions.every(({ canceled }) => canceled)).toBe(true);
    expect(after.fees).toEqual([{ type: 'cancellation', value: FEE_BELOW_CAP }]);
    expect(confirmed(after)).toEqual(confirmed(before));
});

test('UC-06 exc 2 [known defect D-01] a negative cancellation fee is rejected (BVA just below zero)', async ({ page, orders }, testInfo) => {
    // Observed on the baseline: the positions are canceled, a -0.01 cancellation fee is stored, the order total
    // becomes -0.01 and the status stays paid (CancelForm.cancellation_fee has no minimum). The assertions state
    // BR-03 (0 <= fee <= total); test.fail() keeps the suite green while D-01 is open.
    test.fail();
    const alias = 'm3_neg_fee';
    const before = await orders.read(alias);
    expect(before.status).toBe('p');

    await orders.open(alias);
    await openCancelFormByKeyboard(page);
    await untickEmailByKeyboard(page);
    await typeFee(page, FEE_BELOW_ZERO);
    await enterAndWait(page);

    const after = await orders.read(alias);
    await attachState(testInfo, 'persisted-after', after);
    expect(after, 'order must be unchanged after a rejected fee').toEqual(before);
    await expect(page.locator('.form-group.has-error')).toBeVisible();
});
