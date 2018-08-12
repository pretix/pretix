.. highlight:: python
   :linenothreshold: 5

.. _`payment2.0`:

Porting a payment provider from pretix 1.x to pretix 2.x
========================================================

In pretix 2.x, we changed large parts of the payment provider API. This documentation details the changes we made
and shows you how you can make an existing pretix 1.x payment provider compatible with pretix 2.x

Conceptual overview
-------------------

In pretix 1.x, an order was always directly connected to a payment provider for the full life of an order. As long as
an order was unpaid, this could still be changed in some cases, but once an order was paid, no changes to the payment
provider were possible any more. Additionally, the internal state of orders allowed orders only to be fully paid or
not paid at all. This leads to a couple of consequences:

* Payment-related functions (like "execute payment" or "do a refund") always operated on full orders.

* Changing the total of an order was basically impossible once an order was paid, since there was no concept of
  partial payments or partial refunds.

* Payment provider plugins needed to take complicated steps to detect cases that require human intervention, like e.g.

  * An order has expired, no quota is left to revive it, but a payment has been received

  * A payment has been received for a canceled order

  * A payment has been received for an order that has already been paid with a different payment method

  * An external payment service notified us of a refund/dispute

  We noticed that we copied and repeated large portions of code in all our official payment provider plugins, just
  to deal with some of these cases.

* Sometimes, there is the need to mark an order as refunded within pretix, without automatically triggering a refund
  with an external API. Every payment method needed to implement a user interface for this independently.

* If a refund was not possible automatically, there was no way user to track which payments actually have been refunded
  manually and which are still left to do.

* When the payment with one payment provider failed and the user changed to a different payment provider, all
  information about the first payment was lost from the order object and could only be retrieved from order log data,
  which also made it hard to design a data shredder API to get rid of this data.

In pretix 2.x, we introduced two new models, :py:class:`OrderPayment <pretix.base.models.OrderPayment>` and
:py:class:`OrderRefund <pretix.base.models.OrderRefund>`. Each instance of these is connected to an order and
represents one single attempt to pay or refund a specific amount of money. Each one of these has an individual state,
can individually fail or succeed, and carries an amount variable that can differ from the order total.

This has the following advantages:

* The system can now detect orders that are over- or underpaid, independent of the payment providers in use.

* Therefore, we can now allow partial payments, partial refunds, and changing paid orders, and automatically detect
  the cases listed above and notify the user.

Payment providers now interact with those payment and refund objects more than with orders.

Your to-do list
---------------

Payment processing
""""""""""""""""""

* The method ``BasePaymentProvider.order_pending_render`` has been removed and replaced by a new
  ``BasePaymentProvider.payment_pending_render(request, payment)`` method that is passed an ``OrderPayment``
  object instead of an ``Order``.

* The method ``BasePaymentProvider.payment_form_render`` now receives a new ``total`` parameter.

* The method ``BasePaymentProvider.payment_perform`` has been removed and replaced by a new method
  ``BasePaymentProvider.execute_payment(request, payment)`` that is passed an ``OrderPayment``
  object instead of an ``Order``.

* The function ``pretix.base.services.mark_order_paid`` has been removed, instead call ``payment.confirm()``
  on a pending ``OrderPayment`` object. If no further payments are required for this order, this will also
  mark the order as paid automatically. Note that ``payment.confirm()`` can still throw a ``QuotaExceededException``,
  however it will still mark the payment as complete (not the order!), so you should catch this exception and
  inform the user, but not abort the transaction.

* A new property ``BasePaymentProvider.abort_pending_allowed`` has been introduced. Only if set, the user will
  be able to retry a payment or switch the payment method when the order currently has a payment object in
  state ``"pending"``. This replaces ``BasePaymentProvider.order_can_retry``, which no longer exists.

* The methods ``BasePaymentProvider.retry_prepare`` and ``BasePaymentProvider.order_prepare`` have both been
  replaced by a new method ``BasePaymentProvider.payment_prepare(request, payment)`` that is passed an ``OrderPayment``
  object instead of an ``Order``. **Keep in mind that this payment object might have an amount property that
  differs from the order total, if the order is already partially paid.**

* The method ``BasePaymentProvider.order_paid_render`` has been removed.

* The method ``BasePaymentProvider.order_control_render`` has been removed and replaced by a new method
  ``BasePaymentProvider.payment_control_render(request, payment)`` that is passed an ``OrderPayment``
  object instead of an ``Order``.

* There's no need to manually deal with excess payments or duplicate payments anymore, just setting the ``OrderPayment``
  methods to the correct state will do the job.

Creating refunds
""""""""""""""""

* The methods ``BasePaymentProvider.order_control_refund_render`` and ``BasePaymentProvider.order_control_refund_perform``
  have been removed.

* Two new boolean methods ``BasePaymentProvider.payment_refund_supported(payment)`` and ``BasePaymentProvider.payment_partial_refund_supported(payment)``
  have been introduced. They should be set to return ``True`` if and only if the payment API allows to *automatically*
  transfer the money back to the customer.

* A new method ``BasePaymentProvider.execute_refund(refund)`` has been introduced. This method is called using a
  ``OrderRefund`` object in ``"created"`` state and is expected to transfer the money back and confirm success with
  calling ``refund.done()``. This will only ever be called if either ``BasePaymentProvider.payment_refund_supported(payment)``
  or ``BasePaymentProvider.payment_partial_refund_supported(payment)`` return ``True``.

Processing external refunds
"""""""""""""""""""""""""""

* If e.g. a webhook API notifies you that a payment has been disputed or refunded with the external API, you are
  expected to call ``OrderPayment.create_external_refund(self, amount, execution_date, info='{}')`` on this payment.
  This will create and return an appropriate ``OrderRefund`` object and send out a notification. However, it will not
  mark the order as refunded, but will ask the event organizer for a decision.

Data shredders
""""""""""""""

* The method ``BasePaymentProvider.shred_payment_info`` is no longer passed an order, but instead **either**
  an ``OrderPayment`` **or** an ``OrderRefund``.
