Product structure guide
=======================

Between products, categories, variations, add-ons, bundles, and quotas, pretix provides a wide range of features that allow you to set up your event in the way you want it.
However, it is easy to get lost in the process or to get started with building your event right.
Often times, there are multiple ways to do something that come with different advantages and disadvantages.
This guide will walk you through a number of typical examples of pretix event structures and will explain how to set them up – feel free to just skip ahead to a section relevant for you.

Terminology
-----------

Products
    A product is a basic entity that can be bought. You can think of it as a ticket type, but it can be more things than just a ticket, it can also be a piece of merchandise, a parking slot, etc.
    You might find some places where they are called "items" instead, but we're trying to get rid of that.

Product categories
    Products can be sorted into categories. Each product can only be in one category. Category are mostly used for grouping related products together to make your event page easier to read for buyers. However, we'll need categories as well to set up some of the structures outlined below.

Product variations
    During creation of a product, you can decide that your product should have multiple variations. Variations of a product can differ in price, description, and availability, but are otherwise the same. You could use this e.g. for differentiating between a regular ticket and a discounted ticket for students, of when selling merchandise to differentiate the different sizes of a t-shirt.

Product add-ons
    Add-ons are products that are sold together with another product, which we will call the base product in this case. For example, you could have a base product "Conference ticket" and then define multiple workshops that can be chosen as an add-on.

Product bundles
    Bundles work very similarly to add-ons, but are different in the way that they are always automatically included with the base product and cannot be optional. In contrast to add-on products, the same product can be included multiple times in a bundle.

Quotas
    Quotas define the availability of products. A quota has a size (i.e. the number of products in the inventory) and is mapped to one or multiple products or variations.

Questions
    Questions are user-defined form fields that buyers will need to fill out when purchasing a product.

Use case: Multiple price levels
-------------------------------

Imagine you're running a concert with general admission that sells a total of 200 tickets for two prices:

* Regular: € 25.00
* Students: € 19.00

You can either set up two different products called e.g. "Regular ticket" and "Student ticket" with the respective prices, or to variations within the same product. In this simple case, it really doesn't matter.

In addition, you will need quotas. If you do not care how many of your tickets are sold to students, you should set up just **one quota** of 200 called e.g. "General admission" that you link to **both products**.

If you want to limit the number of student tickets to 50 to ensure a certain minimum revenue, but do not want to limit the number of regular tickets artificially, we suggest you to create the same quota of 200 that is linked to both products, and then create a **second quota** of 50 that is only linked to the student ticket. This way, the system will reduce both quotas whenever a student ticket is sold and only the larger quota when a regular ticket is sold.

Use case: Early-bird tiers
--------------------------

Let's say you run a conference that has the following pricing scheme:

* 12 to 6 months before the event: € 450
* 6 to 3 months before the event: € 550
* closer than 3 months to the event: € 650

Of course, you could just set up one product and change its price at the given dates manually, but if you want to set this up automatically, here's how:

Create three products (e.g. "super early bird", "early bird", "regular ticket") with the respective prices and one shared quota of your total event capacity. Then, set the **available from** and **available until** configuration fields of the products to automatically turn them on and off based on the current date.

.. note::

   pretix currently can't do early-bird tiers based on **ticket number** instead of time. We're planning this feature for later in 2019. For now, you'll need to monitor that manually.

Use case: Up-selling of ticket extras
-------------------------------------

Let's assume you're putting up a great music festival, and to save trouble with handling payments on-site, you want to sell parking spaces together with your ticket. By using our add-on feature, you can prompt all users to book the parking space (to make sure they see it) and ensure that only people with a ticket can book a parking space. You can set it up like this:

* Create a base product "Festival admission"
* Create a quota for the base product
* Create a category "Ticket extras" and check "Products in this category are add-on products"
* Create a product "Parking space" within that category
* Create a quota for the parking space product
* Go to the base product and select the tab "Add-Ons" at the top. Click "Add a new add-on" and choose the "Ticket extras" category. You can keep the numbers at 0 and 1.

During checkout, all buyers of the base product will now be prompted if they want to add the parking space.

.. tip::

   You can also use add-on products for free things, just to keep tabs on capacity.

Use case: Conference with workshops
-----------------------------------

When running a conference, you might also organize a number of workshops with smaller capacity. To be able to plan, it would be great to know which workshops an attendee plans to attend.

Your first and simplest option is to just create a multiple-choice question. This has the upside of making it easy for users to change their mind later on, but will not allow you to restrict the number of attendees signing up for a given workshop – or even charge extra for a given workshop.

The usually better option is to go with add-on products. Let's take for example the following conference schedule, in which the lecture can be attended by anyone, but the workshops only have space for 20 persons each:

==================== =================================== ===================================
Time                 Room A                              Room B
==================== =================================== ===================================
Wednesday morning    Lecture
Wednesday afternoon  Workshop A                          Workshop B
Thursday morning     Workshop C                          Workshop D (20 € extra charge)
==================== =================================== ===================================

Assuming you already created one or more products for your general conference admission, we suggest that you additionally create:

* A category called "Workshops" with the checkbox "Products in this category are add-on products" activated

* A free product called "Wednesday afternoon" within the category "Workshops" and with two variations:

    * Workshop A

    * Workshop B

* A free product called "Thursday morning" within the category "Workshops" and with two variations:

    * Workshop C

    * Workshop D with a price of 20 €

* Four quotas for each of the workshops

* One add-on configuration on your base product that allows users to choose between 0 and 2 products from the category "Workshops"

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

Use case: Group discounts
-------------------------

Often times, you want to give discounts for whole groups attending your event. pretix can't automatically discount based on volume, but there's still some ways you can set up group tickets.

Flexible group sizes
""""""""""""""""""""

If you want to give out discounted tickets to groups starting at a given size, but still billed per person, you can do so by creating a special **Group ticket** at the per-person price and set the **Minimum amount per order** option of the ticket to the minimal group size.

This way, your ticket can be bought an arbitrary number of times – but no less than the given minimal amount per order.

Fixed group sizes
"""""""""""""""""

If you want to sell group tickets in fixed sizes, e.g. a table of eight at your gala dinner, you can use product bundles. Assuming you already set up a ticket for admission of single persons, you then set up a second product **Table (8 persons)** with a discounted full price. Then, head to the **Bundled products** tab of that product and add one bundle configuration to include the single admission product **eight times**. Next, create an unlimited quota mapped to the new product.

This way, the purchase of a table will automatically create eight tickets, leading to a correct calculation of your total quota and, as expected, eight persons on your check-in list. You can even ask for the individual names of the persons during checkout.

Use case: Restricted audience
-----------------------------

Not all events are for everyone. Sometimes, there is a good reason to restrict access to your event or parts of your event only to a specific, invited group. There's two ways to implement this with pretix:

Option A: Required voucher codes
""""""""""""""""""""""""""""""""

If you check the option "**This product can only be bought using a voucher**" of one or multiple products, only people holding an applicable voucher code will be able to buy the product.

You can then generate voucher codes for the respective product and send them out to the group of possible attendees. If the recipients should still be able to choose between different products, you can create an additional quota and map the voucher to that quota instead of the products themselves.

There's also the second option "**This product will only be shown if a voucher matching the product is redeemed**". In this case, the existence of the product won't even be shown before a voucher code is entered – useful for a VIP option in a shop where you also sell other products to the general public. Please note that this option does **not** work with vouchers assigned to a quota, only with vouchers assigned directly to the product.

This option is appropriate if you know the group of people beforehand, e.g. members of a club, and you can mail them their access codes.

Option B: Order approvals
"""""""""""""""""""""""""

If you do not know your audience already, but still want to restrict it to a certain group, e.g. people with a given profession, you can check the "**Buying this product requires approval**" in the settings of your product. If a customer tries to buy such a product, they will be able to place their order but can not proceed to payment. Instead, you will be asked to approve or deny the order and only if you approve it, we will send a payment link to the customer.

This requires the customer to interact with the ticket shop twice (once for the order, once for the payment) which adds a little more friction, but gives you full control over who attends the event.

Use case: Mixed taxation
------------------------

Let's say you are a charitable organization in Germany and are allowed to charge a reduced tax rate of 7% for your educational event. However, your event includes a significant amount of food, you might need to charge a 19% tax rate on that portion. For example, your desired tax structure might then look like this:

* Conference ticket price: € 450 (incl. € 150 for food)

    * incl. € 19.63 VAT at 7%
    * incl. € 23.95 VAT at 19%

You can implement this in pretix using product bundles. In order to do so, you should create the following two products:

* Conference ticket at € 450 with a 7% tax rule
* Conference food at € 150 with a 19% tax rule and the option "**Only sell this product as part of a bundle**" set

In addition to your normal conference quota, you need to create an unlimited quota for the food product.

Then, head to the **Bundled products** tab of the "conference ticket" and add the "conference food" as a bundled product with a **designated price** of € 150.

Once a customer tries to buy the € 450 conference ticket, a sub-product will be added and the price will automatically be split into the two components, leading to a correct computation of taxes.