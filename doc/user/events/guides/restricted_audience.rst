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
