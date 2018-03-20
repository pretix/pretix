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

You can find the event deletion button at the bottom of the event settings page. Note however, that it is not possible
to delete an event once any order or invoice has been created, as those likely contain information on financial
transactions which legally may not be tampered with and needs to be kept on record for multiple years in most
countries. In this case, you can just disable the shop by clicking the first square on your event
dashboard.

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

How can I revert a check-in?
----------------------------

Neither our apps nor our web interface can currently undo the check-in of a tickets. We know that this is
inconvenient for some of you, but we have a good reason for it:

Our Desktop and Android apps both support an asynchronous mode in which they can scan tickets while staying
independent of their internet connection. When scanning with multiple devices, it can of course happen that two
devices scan the same ticket without knowing of the other scan. As soon as one of the devices regains connectivity, it
will upload its activity and the server marks the ticket as checked in -- regardless of the order in which the two
scans were made and uploaded (which could be two different orders).

If we'd provide a "check out" feature, it would not only be used to fix an accidental scan, but scan at entry and
exit to count the current number of people inside etc. In this case, the order of operations matters very much for them
to make sense and provide useful results. This makes implementing an asynchronous mode much more complicated.

In this trade off, we chose offline-capabilities over the check out feature. We plan on solving this problem in the
future, but we're not there yet.

If you're just *testing* the check-in capabilities and want to clean out everything for the real process, you can just
delete and re-create the check-in list.
