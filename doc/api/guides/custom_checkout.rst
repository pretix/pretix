Creating an external checkout process
=====================================

Occasionally, we get asked whether it is possible to just use pretix' powerful backend as a ticketing engine but use
a fully-customized checkout process that only communicates via the API. This is possible, but with a few limitations.
If you go down this route, you will miss out on many of pretix features and safeguards, as well as the added flexibility
by most of pretix' plugins. We strongly recommend to talk this through with us before you decide this is the way to go.

However, this is really useful if you need to tightly integrate pretix into existing web applications that e.g. control
the pricing of your products in a way that cannot be mapped to pretix' product structures.

Creating orders
---------------

After letting your user select the products to  buy in your application, you should create a new order object inside
pretix. Below, you can see an example of such an order, but most fields are optional and there are some more features
supported. Read :ref:`rest-orders-create` to learn more about this endpoint.

Please note that this endpoint assumes trustworthy input for the most part. By default, the endpoint checks that
you do not exceed any quotas, do not sell any seats twice, or do not use any redeemed vouchers. However, it will not
complain about violation of any other availability constraints, such as violation of time frames or minimum/maximum
amounts of either your product or event. Bundled products will not be added in automatically and fees will not be
calculated automatically.

.. sourcecode:: http

    POST /api/v1/organizers/democon/events/3vjrh/orders/ HTTP/1.1
    Host: test.pretix.eu
    Accept: application/json, text/javascript
    Content-Type: application/json
    Authorization: …

    {
      "email": "dummy@example.org",
      "locale": "en",
      "sales_channel": "web",
      "payment_provider": "banktransfer",
      "invoice_address": {
        "is_business": false,
        "company": "Sample company",
        "name_parts": {"full_name": "John Doe"},
        "street": "Sesam Street 12",
        "zipcode": "12345",
        "city": "Sample City",
        "country": "US",
        "state": "NY",
        "internal_reference": "",
        "vat_id": ""
      },
      "positions": [
        {
          "item": 21,
          "variation": null,
          "attendee_name_parts": {
            "full_name": "Peter"
          },
          "answers": [
            {
              "question": 1,
              "answer": "23",
              "options": []
            }
          ],
          "subevent": null
        }
      ],
      "fees": []
    }

You will be returned a full order object that you can inspect, store, or use to build emails or confirmation pages for
the user. If you don't want to do that yourself, it will also contain the URL to our confirmation page in the ``url``
attribute. If you pass the ``"send_mail": true`` option, pretix will also send order confirmations for you.

Handling payments yourself
--------------------------

If you want to handle payments in your application, you can either just create the orders with status "paid" or you can
create them in "pending" state (the default) and later confirm the payment. We strongly advise to use the payment
provider ``"manual"`` in this case to avoid interference with payment code with pretix.

However, it is often unfeasible to implement the payment process yourself, and it also requires you to give up a
lot of pretix functionality, such as automatic refunds. Therefore, it is also possible to utilize pretix' native
payment process even in this case:

Using pretix payment providers
------------------------------

If you passed a ``payment_provider`` during order creation above, pretix will have created a payment object with state
``created`` that you can see in the returned order object. This payment object will have an attribute ``payment_url``
that you can use to let the user pay. For example, you could link or redirect to this page.

If you want the user to return to your application after the payment is complete, you can pass a query parameter
``return_url``. To prepare your event for this, open your event in the pretix backend and go to "Settings", then
"Plugins". Enable the plugin "Redirection from order page". Then, go to the new page "Settings", then "Redirection".
Enter the base URL of your web application. This will allow you to redirect to pages under this base URL later on.
For example, if you want users to be redirected to ``https://example.org/order/return?tx_id=1234``, you could now
either enter ``https://example.org`` or ``https://example.org/order/``.

The user will be redirected back to your page instead of pretix' order confirmation page after the payment,
**regardless of whether it was successful or not**. Make sure you use our API to check if the payment actually
worked! Your final URL could look like this::

    https://test.pretix.eu/democon/3vjrh/order/NSLEZ/ujbrnsjzbq4dzhck/pay/123/?return_url=https%3A%2F%2Fexample.org%2Forder%2Freturn%3Ftx_id%3D1234

You can also embed this page in an ``<iframe>`` instead. Note, however, that this causes problems with some payment
methods such as PayPal which do not allow being opened in an iframe. pretix can partly work around these issues by
opening a new window, but will only to so if you also append an ``iframe=1`` parameter to the URL::

    https://test.pretix.eu/democon/3vjrh/order/NSLEZ/ujbrnsjzbq4dzhck/pay/123/?return_url=https%3A%2F%2Fexample.org%2Forder%2Freturn%3Ftx_id%3D1234&iframe=1

If you did **not** pass a payment method since you want us to ask the user which payment method they want to use, you
need to construct the URL from the ``url`` attribute of the order and the sub-path ``pay/change```. For example, you
would end up with the following URL::

    https://test.pretix.eu/democon/3vjrh/order/NSLEZ/ujbrnsjzbq4dzhck/pay/change

Of course, you can also use the ``iframe`` and ``return_url`` parameters here.

Optional: Cart reservations
---------------------------

Creating orders is an atomic operation: The order is either created as a whole or not at all. However, pretix'
built-in checkout automatically reserves tickets in a user's cart for a configurable amount of time to ensure users
will actually get their tickets once they started entering all their details. If you want a similar behavior in your
application, you need to create :ref:`rest-carts` through the API.

When creating your order, you can pass a ``consume_carts`` parameter with the cart ID(s) of your user. This way, the
quota reserved by the cart will be credited towards the order and the carts will be destroyed if (and only if) the
order creation succeeds.

Cart creation is currently even more limited than the order creation endpoints, as cart creation currently does not
support vouchers or automatic price calculation. If you require these features, please get in touch with us.
