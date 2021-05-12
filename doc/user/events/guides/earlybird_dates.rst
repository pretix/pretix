Use case: Early-bird tiers based on dates
-----------------------------------------

Let's say you run a conference that has the following pricing scheme:

* 12 to 6 months before the event: € 450
* 6 to 3 months before the event: € 550
* closer than 3 months to the event: € 650

Of course, you could just set up one product and change its price at the given dates manually, but if you want to set this up automatically, here's how:

Create three products (e.g. "super early bird", "early bird", "regular ticket") with the respective prices and one shared quota of your total event capacity. Then, set the **available from** and **available until** configuration fields of the products to automatically turn them on and off based on the current date.
