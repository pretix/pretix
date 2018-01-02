FAQ and Troubleshooting
=======================

How can I test my shop before taking it live?
---------------------------------------------

There are multiple ways to do this.

First, you could just create some orders in your real shop and cancel/refund them later. If you don't want to process
real payments for the tests, you can either use a "manual" payment method like bank transfer and just mark the orders
as paid with the button in the backend, or if you want to use e.g. Stripe, you can configure pretix to use your keys
for the Stripe test system and use their test credit cars. Read our :ref:`Stripe documentation <stripe>` for more
information.

Second, you could create a separate event, just for testing. In the last step of the :ref:`event creation process <event_create>`,
you can specify that you want to copy all settings from your real event, so you don't have to do all of it twice.

We are planning to add a dedicated test mode in a later version of pretix.

If you are using the hosted service at pretix.eu and want to get rid of the test orders completely, contact us at
support@pretix.eu and we can remove them for you. Please note that we only are able to do that *before* you have
received any real orders (i.e. taken the shop public). We won't charge any fees for test orders or test events.

How do I delete an event?
-------------------------

It is currently not possible to delete events, you can just disable the shop by clicking the first square on your event
dashboard. Events can't be deleted as they most likely contain information on financial transactions which legally
needs to be kept on record for multiple years in most countries.

If you are using the hosted service at pretix.eu and want to get rid of an event that you only used for testing, contact
us at support@pretix.eu and we can remove it for you.

Why doesn't my product show up in the ticket shop?
--------------------------------------------------

If you created a product and it doesn't show up, please follow the following steps to find out why:

1. Check if the product's "active" checkbox is enabled.
2. Check if the product is in a category that has the "Products in this category are add-on products" checkbox enabled.
   If this is the case, the product won't show up on the shop front page, but only in the first step of checkout when
   a product in the cart allows to add add-on products from this category.
3. Check if the product's "Available from" or "Available until" settings restrict it to a date range.
4. Check if the product's checkbox "This product will only be shown if a voucher matching the product is redeemed." is
   enabled. If this is the case, the product will only be shown if the customer redeems a voucher that *directly* matches
   to this product. It will not be shown if the voucher only is configured to match a quota that contains the product.
5. Check that a quota exists that contains this product. If your product has variations, check that at least one
   variation is contained in a quota. If your event is an event series, make sure that the product is contained in a
   quota that is assigned to the series date that you access the shop for.
6. If the sale period has not started yet or is already over, check the "Show items outside presale period" setting of
   your event.
