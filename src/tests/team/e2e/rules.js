// Business-rule constants used by Member 3's Orders browser tests.
// A rule change (for example a new fee cap) is made here once; every dependent test follows.

/** Every seeded order costs EUR 20.00 (sqe/orders_fixtures.py TOTAL). */
export const ORDER_TOTAL = '20.00';

/** BR-03: the cancellation fee may not exceed the order total. */
export const FEE_CAP = ORDER_TOTAL;

/** BR-03 boundary values around the upper limit (3-point BVA). */
export const FEE_BELOW_CAP = '19.99';
export const FEE_ABOVE_CAP = '20.01';

/** BR-03 lower limit: a fee cannot be negative. 0.00 is "at", -0.01 is "just below". */
export const FEE_AT_ZERO = '0.00';
export const FEE_BELOW_ZERO = '-0.01';

/** Payment amounts for UC-05 (W1). */
export const PARTIAL_PAYMENT = '12.00';
export const REMAINING_AFTER_PARTIAL = '8.00';
export const OVERPAYMENT = '25.00';
export const NEGATIVE_PAYMENT = '-0.01';
export const INVALID_DATE = '2026-13-45';

/** Messages the application shows. */
export const MSG = {
    paymentCreated: 'The payment has been created successfully.',
    canceled: 'The order has been canceled.',
    feeAboveTotal: 'The cancellation fee cannot be higher than the total amount of this order.',
};
