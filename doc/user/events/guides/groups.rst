Use case: Group discounts
-------------------------

Often times, you want to give discounts for whole groups attending your event. pretix can't automatically discount based on volume, but there's still some ways you can set up group tickets.

Flexible group sizes
""""""""""""""""""""

If you want to give out discounted tickets to groups starting at a given size, but still billed per person, you can do so by creating a special **Group ticket** at the per-person price and set the **Minimum amount per order** option of the ticket to the minimal group size.

For more complex use cases, you can also use add-on products that can be chosen multiple times.

This way, your ticket can be bought an arbitrary number of times – but no less than the given minimal amount per order.

Fixed group sizes
"""""""""""""""""

If you want to sell group tickets in fixed sizes, e.g. a table of eight at your gala dinner, you can use product bundles. Assuming you already set up a ticket for admission of single persons, you then set up a second product **Table (8 persons)** with a discounted full price. Then, head to the **Bundled products** tab of that product and add one bundle configuration to include the single admission product **eight times**. Next, create an unlimited quota mapped to the new product.

This way, the purchase of a table will automatically create eight tickets, leading to a correct calculation of your total quota and, as expected, eight persons on your check-in list. You can even ask for the individual names of the persons during checkout.
