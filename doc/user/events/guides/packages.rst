Use case: Discounted packages
-----------------------------

Imagine you run a trade show that opens on three consecutive days and you want to have the following pricing:

* Single day: € 10
* Any two days: € 17
* All three days:  € 25

In this case, there are multiple different ways you could set this up with pretix.

Option A: Combination products
""""""""""""""""""""""""""""""

With this option, you just set up all the different combinations someone could by as a separate product. In this case, you would need 7 products:

* Day 1 pass
* Day 2 pass
* Day 3 pass
* Day 1+2 pass
* Day 2+3 pass
* Day 1+3 pass
* All-day pass

Then, you create three quotas, each one with the maximum capacity of your venue on any given day:

* Day 1 quota, linked to "Day 1 pass", "Day 1+2 pass", "Day 1+3 pass", and "All-day pass"
* Day 2 quota, linked to "Day 2 pass", "Day 1+2 pass", "Day 2+3 pass", and "All-day pass"
* Day 3 quota, linked to "Day 3 pass", "Day 2+3 pass", "Day 1+3 pass", and "All-day pass"

This way, every person gets exactly one ticket that they can use for all days that they attend. You can later set up check-in lists appropriately to make sure only tickets valid for a certain day can be scanned on that day.

The benefit of this option is that your product structure and order structure stays very simple. However, the two-day packages scale badly when you need many products.

We recommend this setup for most setups in which the number of possible combinations does not exceed the number of parts (here: number of days) by much.

Option B: Add-ons and bundles
"""""""""""""""""""""""""""""

We can combine the two features "product add-ons" and "product bundles" to set this up in a different way. Here, you would create the following five products:

* Day 1 pass in a category called "Day passes"
* Day 2 pass in a category called "Day passes"
* Day 3 pass in a category called "Day passes"
* Two-day pass
* All-day pass

This time, you will need five quotas:

* Day 1 quota, linked to "Day 1 pass"
* Day 2 quota, linked to "Day 2 pass"
* Day 3 quota, linked to "Day 3 pass"
* Two-day pass quota, linked to "Two-day pass" (can be unlimited)
* All-day pass quota, linked to "All-day pass" (can be unlimited)

Then, you open the "Add-On" tab in the settings of the **Two-day pass** product and create a new add-on configuration specifying the following options:

* Category: "Day passes"
* Minimum number: 2
* Maximum number: 2
* Add-Ons are included in the price: Yes

This way, when buying a two-day pass, the user will be able to select *exactly* two days for free, which will then be added to the cart. Depending on your specific configuration, the user will now receive *two separate* tickets, one for each day.

For the all-day pass, you open the "Bundled products" tab in the settings of the **All-day pass** product and add **three** new bundled items with the following options:

* Bundled product: "Day 1/2/3"
* Bundled variation: None
* Count: 1
* Designated price: 0

This way, when buying an all-day pass, three free day passes will *automatically* be added to the cart. Depending on your specific configuration, the user will now receive *three separate* tickets, one for each day.

This approach makes your order data more complicated, since e.g. someone who buys an all-day pass now technically bought **four products**. However, this option allows for more flexibility when you have lots of options to choose from.

.. tip::

   Depending on the packages you offer, you **might not need both the add-on and the bundle feature**, i.e. you only need the add-on feature for the two-day pass and only the bundle feature for the all-day pass. You could also set up the two-day pass like we showed here, but the all-day pass like in option A!
