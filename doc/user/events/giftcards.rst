.. spelling::

   Warengutschein
   Wertgutschein

.. _giftcards:

Gift cards
==========

Gift cards, also known as "gift coupons" or "gift certificates" are a mechanism that allows you to sell tokens that
can later be used to pay for tickets.

Gift cards are very different feature than **vouchers**. The difference is:

* Vouchers can be used to give a discount. When a voucher is used, the price of a ticket is reduced by the configured
  discount and sold at a lower price. They therefore reduce both revenue as well as taxes. Vouchers (in pretix) are
  always specific to a certain product in an order. Vouchers are usually not sold but given out as part of a
  marketing campaign or to specific groups of people. Vouchers in pretix are bound to a specific event.

* Gift cards are not a discount, but rather a means of payment. If you buy a €20 ticket with a €10 gift card, it is
  still a €20 ticket and will still count towards your revenue with €20. Gift cards are usually bought for the money
  that they are worth. Gift cards in pretix can be used across events (and even organizers).

Selling gift cards
------------------

Selling gift cards works like selling every other type of product in pretix: Create a new product, then head to
"Additional settings" and select the option "This product is a gift card". Whenever someone buys this product and
pays for it, a new gift card will be created.

In this case, the gift card code corresponds to the "ticket secret" in the PDF ticket. Therefore, if selling gift cards,
you can use ticket downloads just as with normal tickets and use our ticket editor to create beautiful gift certificates
people can give to their loved ones.

Of course, you can use pretix' flexible options to modify your product. For example, you can configure that the customer
can freely choose the price of the gift card.

.. note::

   pretix currently does not support charging sales tax or VAT when selling gift cards, but instead charges VAT on
   the full price when the gift card is redeemed. This is the correct behavior in Germany and some other countries for
   gift cards which are not bound to a very specific service ("Warengutschein"), but instead to a monetary amount
   ("Wertgutschein").

.. note::

   The ticket PDF will not contain the correct gift card code before the order has been paid, so we recommend not
   selling gift cards in events where tickets are issued before payments arrive.


Accepting gift cards
--------------------

All your events have have the payment provider "Gift card" enabled by default, but it will only show up in the ticket
shop once the very first gift card has been issued on your organizer account. Of course, you can turn off gift card
payments if you do not want them for a specific event.

If gift card payments are enabled, buyers will be able to select "Gift card" as a payment method during checkout. If
a gift card with a value less than the order total is used, the buyer will be asked to select a second payment method
for the remaining payment. If a gift card with a value greater than the order total is used, the surplus amount
remains on the gift card and can be used in a different purchase.

If it possible to accept gift cards across organizer accounts. To do so, you need to have access to both organizer
accounts. Then, you will see a configuration section at the bottom of the "Gift cards" page of your organizer settings
where you can specify which gift cards should be accepted.

Manually issuing or using gift cards
------------------------------------

Of course, you can also issue or redeem gift cards manually through our backend using the "Gift cards" menu item in your
organizer profile or using our API. These gift cards will be tracked by pretix, but do not correspond to any purchase
within pretix. You will therefore need to account for them in your books separately.
