Use case: Group discounts
-------------------------

Often times, you want to give discounts for whole groups attending your event.

Automatic discounts
"""""""""""""""""""

pretix can automatically grant discounts if a certain condition is met, such as a specific group size. To set this up,
head to **Products**, **Discounts** in the event navigation and **Create a new discount**. You can choose a name so you
can later find this again. You can also optionally restrict the discount to a specific time frame or a specific sales
channel.

Next, either select **Apply to all products** or create a selection of products that are eligible for the discount.

For a **percentual group discount** similar to "if you buy at least 5 tickets, you get 20 percent off", set
**Minimum number of matching products** to "5" and **Percentual discount on matching products** to "20.00".

For a **buy-X-get-Y discount**, e.g. "if you buy 4 tickets, you get the 5th one free", set
**Minimum number of matching products** to "5", **Percentual discount on matching products** to "100.00", and
**Apply discount only to this number of matching products** to "1".

Fixed group packages
""""""""""""""""""""

If you want to sell group tickets in fixed sizes, e.g. a table of eight at your gala dinner, you can use product bundles.
Assuming you already set up a ticket for admission of single persons, you then set up a second product **Table (8 persons)**
with a discounted full price. Then, head to the **Bundled products** tab of that product and add one bundle configuration
to include the single admission product **eight times**. Next, create an unlimited quota mapped to the new product.

This way, the purchase of a table will automatically create eight tickets, leading to a correct calculation of your total
quota and, as expected, eight persons on your check-in list. You can even ask for the individual names of the persons
during checkout.

Minimum order amount
""""""""""""""""""""

If you want to promote discounted group tickets in your price list, you can also do so by creating a special
**Group ticket** at the reduced per-person price and set the **Minimum amount per order** option of the ticket to the minimal
group size.

For more complex use cases, you can also use add-on products that can be chosen multiple times.

This way, your ticket can be bought an arbitrary number of times – but no less than the given minimal amount per order.
