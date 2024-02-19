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

