.. _`algorithms-pricing`:

Pricing algorithms
==================

With pretix being an e-commerce application, one of its core tasks is to determine the price of a purchase. With the
complexity allowed by our range of features, this is not a trivial task and there are many edge cases that need to be
clearly defined. The most challenging part about this is that there are many situations in which a price might change
while the user is going through the checkout process and we're learning more information about them or their purchase.
For example, prices change when

* The cart expires and the listed prices changed in the meantime
* The user adds an invoice address that triggers a change in taxation
* The user chooses a custom price for an add-on product and adjusts the price later on
* The user adds a voucher to their cart
* An automatic discount is applied

For the purposes of this page, we're making a distinction between "naive prices" (which are just a plain number like 23.00), and
"taxed prices" (which are a combination of a net price, a tax rate, and a gross price, like 19.33 + 19% = 23.00).

Computation of listed prices
----------------------------

When showing a list of products, e.g. on the event front page, we always need to show a price. This price is what we
call the "listed price" later on.

To compute the listed price, we first use the ``default_price`` attribute of the ``Item`` that is being shown.
If we are showing an ``ItemVariation`` and that variation has a ``default_price`` set on itself, the variation's price
takes precedence and replaces the item's price.
If we're in an event series and there exists a ``SubEventItem`` or ``SubEventItemVariation`` with a price set, the
subevent's price configuration takes precedence over both the item as well as the variation and replaces the listed price.

Listed prices are naive prices. Before we actually show them to the user, we need to check if ``TaxRule.price_includes_tax``
is set to determine if we need to add tax or subtract tax to get to the taxed price. We then consider the event's
``display_net_prices`` setting to figure out which way to present the taxed price in the interface.

Guarantees on listed prices
---------------------------

One goal of all further logic is that if a user sees a listed price, they are guaranteed to get the product at that
price as long as they complete their purchase within the cart expiration time frame. For example, if the cart expiration
time is set to 30 minutes and someone puts a item listed at €23 in their cart at 4pm, they can still complete checkout
at €23 until 4.30pm, even if the organizer decides to raise the price to €25 at 4.10pm. If they complete checkout after
4.30pm, their cart will be adjusted to the new price and the user will see a warning that the price has changed.

Computation of cart prices
--------------------------

Input
"""""

To ensure the guarantee mentioned above, even in the light of all possible dynamic changes, the ``listed_price``
is explicitly stored in the ``CartPosition`` model after the item has been added to the cart.

If ``Item.free_price`` is set, the user is allowed to voluntarily increase the price. In this case, the user's input
is stored as ``custom_price_input`` without much further validation for use further down below in the process.
If ``display_net_prices`` is set, the user's input is also considered to be a net price and ``custom_price_input_is_net``
is stored for the cart position. In any other case, the user's input is considered to be a gross price based on the tax
rules' default tax rate.

The computation of prices in the cart always starts from the ``listed_price``. The ``list_price`` is only computed
when adding the product to the cart or when extending the cart's lifetime after it expired. All other steps such as
creating an order based on the cart trust ``list_price`` without further checks.

Vouchers
""""""""

As a first step, the cart is checked for any voucher that should be applied to the position. If such a voucher exists,
it's discount (percentage or fixed) is applied to the listed price. The result of this is stored to ``price_after_voucher``.
Since ``listed_price`` naive, ``price_after_voucher`` is naive as well. As a consequence, if you have a voucher configured
to "set the price to €10", it depends on ``TaxRule.price_includes_tax`` again whether this is €10 including or excluding
taxes.

The ``price_after_voucher`` is only computed when adding the product to the cart or when extending the cart's
lifetime after it expired. It is also checked again when the order is created, since the available discount might have
changed due to the voucher's budget being (almost) exhausted.

Line price
""""""""""

The next step computes the final price of this position if it is the only position in the cart. This happens in "reverse
order", i.e. before the computation can be performed for a cart position, the step needs to be performed on all of its
bundled positions. The sum of ``price_after_voucher`` of all bundled positions is now called ``bundled_sum``.

First, the value from ``price_after_voucher`` will be processed by the applicable ``TaxRule.tax()`` (which is complex
in itself but is not documented here in detail at the moment).

If ``custom_price_input`` is not set, ``bundled_sum`` will be subtracted from the gross price and the net price is
adjusted accordingly. The result is stored as ``tax_rate`` and ``line_price_gross`` in the cart position.

If ``custom_price_input`` is set, the value will be compared to either the gross or the net value of the ``tax()``
result, depending on ``custom_price_input_is_net``. If the comparison yields that the custom price is higher, ``tax()``
will be called again . Then, ``bundled_sum`` will be subtracted from the gross price and the result is stored like
above.

The computation of ``line_price_gross`` from ``price_after_voucher``, ``custom_price_input``, and tax settings
is repeated after every change of anything in the cart or after every change of the invoice address.

Discounts
---------

After ``line_price_gross`` has been computed for all positions, the discount engine will run to apply any automatic
discounts. Organizers can add rules for automatic discounts in the pretix backend. These rules are ordered and
will be applied in order. Every cart position can only be "used" by one discount rule. "Used" can either mean that
the price of the position was actually discounted, but it can also mean that the position was required to enable
a discount for a different position, e.g. in case of a "buy 3 for the price of 2" offer.

The algorithm for applying an individual discount rule first starts with eliminating all products that do not match
the rule based on its product scope. Then, the algorithm is handled differently for different configurations.

Case 1: Discount based on minimum value without respect to subevents
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

* Check whether the gross sum of all positions is at least ``condition_min_value``, otherwise abort.

* Reduce the price of all positions by ``benefit_discount_matching_percent``.

* Mark all positions as "used" to hide them from further rules

Case 2: Discount based on minimum number of tickets without respect to subevents
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

* Check whether the number of all positions is at least ``condition_min_count``, otherwise abort.

* If ``benefit_only_apply_to_cheapest_n_maches`` is set,

    * Sort all positions by price.
    * Reduce the price of the first ``n_positions // condition_min_count * benefit_only_apply_to_cheapest_n_matches`` positions by ``benefit_discount_matching_percent``.
    * Mark the first ``n_positions // condition_min_count * condition_min_count`` as "used" to hide them from further rules.
    * Mark all positions as "used" to hide them from further rules.

* Else,

    * Reduce the price of all positions by ``benefit_discount_matching_percent``.
    * Mark all positions as "used" to hide them from further rules.

Case 3: Discount only for products of the same subevent
"""""""""""""""""""""""""""""""""""""""""""""""""""""""

* Split the cart into groups based on the subevent.

* Proceed with case 1 or 2 for every group.

Case 4: Discount only for products of distinct subevents
""""""""""""""""""""""""""""""""""""""""""""""""""""""""

* Let ``subevents`` be a list of distinct subevents in the cart.

* Let ``positions[subevent]`` be a list of positions for every subevent.

* Let ``current_group`` be the current group and ``groups`` the list of all groups.

* Repeat

    * Order ``subevents`` by the length of their ``positions[subevent]`` list, starting with the longest list.
      Do not count positions that are part of ``current_group`` already.

    * Let ``candidates`` be the concatenation of all ``positions[subevent]`` lists with the same length as the
      longest list.

    * If ``candidates`` is empty, abort the repetition.

    * Order ``candidates`` by their price, starting with the lowest price.

    * Pick one entry from ``candidates`` and put it into ``current_group``. If ``current_group`` is shorter than
      ``benefit_only_apply_to_cheapest_n_matches``, we pick from the start (lowest price), otherwise we pick from
      the end (highest price)

    * If ``current_group`` is now ``condition_min_count``, remove all entries from ``current_group`` from
      ``positions[…]``, add ``current_group`` to ``groups``, and reset ``current_group`` to an empty group.

* For every position still left in a ``positions[…]`` list, try if there is any ``group`` in groups that it can
  still be added to without violating the rule of distinct subevents

* For every group in ``groups``, proceed with case 1 or 2.

Flowchart
---------

.. image:: /images/cart_pricing.png


.. _`algorithms-rounding`:

Rounding of taxes
-----------------

pretix internally always stores taxes on a per-line level, like this:

 ========== ========== =========== ======= =============
   Product   Tax rate   Net price     Tax   Gross price
 ========== ========== =========== ======= =============
  Ticket A       19 %       84.03   15.97        100.00
  Ticket B       19 %       84.03   15.97        100.00
  Ticket C       19 %       84.03   15.97        100.00
  Ticket D       19 %       84.03   15.97        100.00
  Ticket E       19 %       84.03   15.97        100.00
       Sum                 420.15   79.85        500.00
 ========== ========== =========== ======= =============

Whether the net price is computed from the gross price or vice versa is configured on the tax rule and may differ for every line.

The line-based computation has a few significant advantages:

- We can report both net and gross prices for every individual ticket.

- We can report both net and gross prices for every filter imaginable, such as the gross sum of all sales of Ticket A
  or the net sum of all sales for a specific date in an event series. All numbers will be exact.

- When splitting the order into two, both net price and gross price are split without any changes in rounding.

The main disadvantage is that the tax looks "wrong" when computed from the sum. Taking the sum of net prices (420.15)
and multiplying it with the tax rate (19%) yields a tax amount of 79.83 (instead of 79.85) and a gross sum of 499.98
(instead of 500.00). This becomes a problem when juristictions, data formats, or external systems expect this calculation
to work on the level of the entire order. A prominent example is the EN 16931 standard for e-invoicing that
does not allow the computation as created by pretix.

However, calculating the tax rate from the net total has significant disadvantages:

- It is impossible to guarantee a stable gross price this way, i.e. if you advertise a price of €100 per ticket to
  consumers, they will be confused when they only need to pay €499.98 for 5 tickets.

- Some prices are impossible, e.g. you cannot sell a ticket for a gross price of €99.99 at a 19% tax rate, since there
  is no two-decimal net price that would be computed to a gross price of €99.99.

- When splitting an order into two, the combined of the new orders is not guaranteed to be the same as the total of the
  original order. Therefore, additional payments or refunds of very small amounts might be necessary.

To allow organizers to make their own choices on this matter, pretix provides the following options:

Compute taxes for every line individually
"""""""""""""""""""""""""""""""""""""""""

Algorithm identifier: ``line``

This is our original algorithm where the tax value is rounded for every line individually.

**This is our current default algorithm and we recommend it whenever you do not have different requirements** (see below).
For the example above:

 ========== ========== =========== ======= =============
   Product   Tax rate   Net price     Tax   Gross price
 ========== ========== =========== ======= =============
  Ticket A       19 %       84.03   15.97        100.00
  Ticket B       19 %       84.03   15.97        100.00
  Ticket C       19 %       84.03   15.97        100.00
  Ticket D       19 %       84.03   15.97        100.00
  Ticket E       19 %       84.03   15.97        100.00
       Sum                 420.15   79.85        500.00
 ========== ========== =========== ======= =============


Compute taxes based on net total
""""""""""""""""""""""""""""""""

Algorithm identifier: ``sum_by_net``

In this algorithm, the tax value and gross total are computed from the sum of the net prices. To accomplish this within
our data model, the gross price and tax of some of the tickets will be changed by the minimum currency unit (e.g. €0.01).
The net price of the tickets always stay the same.

**This is the algorithm intended by EN 16931 invoices and our recommendation to use for e-invoicing when (primarily) business customers are involved.**

The main downside is that it might be confusing when selling to consumers, since the amounts to be paid change in unexpected ways.
For the example above, the customer expects to pay 5 times 100.00, but they are are in fact charged 499.98:

 ========== ========== =========== ============================== ==============================
   Product   Tax rate   Net price                            Tax                    Gross price
 ========== ========== =========== ============================== ==============================
  Ticket A       19 %       84.03   15.96 (incl. -0.01 rounding)   99.99 (incl. -0.01 rounding)
  Ticket B       19 %       84.03   15.96 (incl. -0.01 rounding)   99.99 (incl. -0.01 rounding)
  Ticket C       19 %       84.03                          15.97                         100.00
  Ticket D       19 %       84.03                          15.97                         100.00
  Ticket E       19 %       84.03                          15.97                         100.00
       Sum                 420.15                          78.83                         499.98
 ========== ========== =========== ============================== ==============================

Compute taxes based on net total with stable gross prices
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""

Algorithm identifier: ``sum_by_net_keep_gross``

In this algorithm, the tax value and gross total are computed from the sum of the net prices. However, the net prices
of some of the tickets will be changed automatically by the minimum currency unit (e.g. €0.01) such that the resulting
gross prices stay the same.

**This is less confusing to consumers and the end result is still compliant to EN 16931, so we recommend this for e-invoicing when (primarily) consumers are involved.**

The main downside is that it might be confusing when selling to business customers, since the prices of the identical tickets appear to be different.
Full computation for the example above:

 ========== ========== ============================= ============================== =============
   Product   Tax rate                     Net price                            Tax   Gross price
 ========== ========== ============================= ============================== =============
  Ticket A       19 %   84.04 (incl. 0.01 rounding)   15.96 (incl. -0.01 rounding)        100.00
  Ticket B       19 %   84.04 (incl. 0.01 rounding)   15.96 (incl. -0.01 rounding)        100.00
  Ticket C       19 %                         84.03                          15.97        100.00
  Ticket D       19 %                         84.03                          15.97        100.00
  Ticket E       19 %                         84.03                          15.97        100.00
       Sum                                   420.17                          79.83        500.00
 ========== ========== ============================= ============================== =============
