.. spelling:: checkins

Orders
======

Order resource
--------------

The order resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
code                                  string                     Order code
status                                string                     Order status, one of:

                                                                 * ``n`` – pending
                                                                 * ``p`` – paid
                                                                 * ``e`` – expired
                                                                 * ``c`` – canceled
                                                                 * ``r`` – refunded
secret                                string                     The secret contained in the link sent to the customer
email                                 string                     The customer email address
locale                                string                     The locale used for communication with this customer
datetime                              datetime                   Time of order creation
expires                               datetime                   The order will expire, if it is still pending by this time
payment_date                          date                       Date of payment receipt
payment_provider                      string                     Payment provider used for this order
total                                 money (string)             Total value of this order
comment                               string                     Internal comment on this order
checkin_attention                     boolean                    If ``True``, the check-in app should show a warning
                                                                 that this ticket requires special attention if a ticket
                                                                 of this order is scanned.
invoice_address                       object                     Invoice address information (can be ``null``)
├ last_modified                       datetime                   Last modification date of the address
├ company                             string                     Customer company name
├ is_business                         boolean                    Business or individual customers (always ``False``
                                                                 for orders created before pretix 1.7, do not rely on
                                                                 it).
├ name                                string                     Customer name
├ street                              string                     Customer street
├ zipcode                             string                     Customer ZIP code
├ city                                string                     Customer city
├ country                             string                     Customer country
├ internal_reference                  string                     Customer's internal reference to be printed on the invoice
├ vat_id                              string                     Customer VAT ID
└ vat_id_validated                    string                     ``True``, if the VAT ID has been validated against the
                                                                 EU VAT service and validation was successful. This only
                                                                 happens in rare cases.
positions                             list of objects            List of order positions (see below)
fees                                  list of objects            List of fees included in the order total (i.e.
                                                                 payment fees)
├ fee_type                            string                     Type of fee (currently ``payment``, ``passbook``,
                                                                 ``other``)
├ value                               money (string)             Fee amount
├ description                         string                     Human-readable string with more details (can be empty)
├ internal_type                       string                     Internal string (i.e. ID of the payment provider),
                                                                 can be empty
├ tax_rate                            decimal (string)           VAT rate applied for this fee
├ tax_value                           money (string)             VAT included in this fee
└ tax_rule                            integer                    The ID of the used tax rule (or ``null``)
downloads                             list of objects            List of ticket download options for order-wise ticket
                                                                 downloading. This might be a multi-page PDF or a ZIP
                                                                 file of tickets for outputs that do not support
                                                                 multiple tickets natively. See also order position
                                                                 download options.
├ output                              string                     Ticket output provider (e.g. ``pdf``, ``passbook``)
└ url                                 string                     Download URL
last_modified                         datetime                   Last modification of this object
===================================== ========================== =======================================================


.. versionchanged:: 1.6

   The ``invoice_address.country`` attribute contains a two-letter country code for all new orders. For old orders,
   a custom text might still be returned.

.. versionchanged:: 1.7

   The attributes ``invoice_address.vat_id_validated`` and ``invoice_address.is_business`` have been added.
   The attributes ``order.payment_fee``, ``order.payment_fee_tax_rate`` and ``order.payment_fee_tax_value`` have been
   deprecated in favor of the new ``fees`` attribute but will still be served and removed in 1.9.

.. versionchanged:: 1.9

   First write operations (``…/mark_paid/``, ``…/mark_pending/``, ``…/mark_canceled/``, ``…/mark_expired/``) have been added.
   The attribute ``invoice_address.internal_reference`` has been added.

.. versionchanged:: 1.13

   The field ``checkin_attention`` has been added.

.. versionchanged:: 1.15

   The attributes ``order.payment_fee``, ``order.payment_fee_tax_rate``, ``order.payment_fee_tax_value`` and
   ``order.payment_fee_tax_rule`` have finally been removed.

.. versionchanged:: 1.16

   The attributes ``order.last_modified`` as well as the corresponding filters to the resource have been added.
   An endpoint for order creation has been added.

.. _order-position-resource:

Order position resource
-----------------------

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the order position
order                                 string                     Order code of the order the position belongs to
positionid                            integer                    Number of the position within the order
item                                  integer                    ID of the purchased item
variation                             integer                    ID of the purchased variation (or ``null``)
price                                 money (string)             Price of this position
attendee_name                         string                     Specified attendee name for this position (or ``null``)
attendee_email                        string                     Specified attendee email address for this position (or ``null``)
voucher                               integer                    Internal ID of the voucher used for this position (or ``null``)
tax_rate                              decimal (string)           VAT rate applied for this position
tax_value                             money (string)             VAT included in this position
tax_rule                              integer                    The ID of the used tax rule (or ``null``)
secret                                string                     Secret code printed on the tickets for validation
addon_to                              integer                    Internal ID of the position this position is an add-on for (or ``null``)
subevent                              integer                    ID of the date inside an event series this position belongs to (or ``null``).
checkins                              list of objects            List of check-ins with this ticket
├ list                                integer                    Internal ID of the check-in list
└ datetime                            datetime                   Time of check-in
downloads                             list of objects            List of ticket download options
├ output                              string                     Ticket output provider (e.g. ``pdf``, ``passbook``)
└ url                                 string                     Download URL
answers                               list of objects            Answers to user-defined questions
├ question                            integer                    Internal ID of the answered question
├ answer                              string                     Text representation of the answer
├ question_identifier                 string                     The question's ``identifier`` field
├ options                             list of integers           Internal IDs of selected option(s)s (only for choice types)
└ option_identifiers                  list of strings            The ``identifier`` fields of the selected option(s)s
===================================== ========================== =======================================================

.. versionchanged:: 1.7

   The attribute ``tax_rule`` has been added.

.. versionchanged:: 1.11

   The attribute ``checkins.list`` has been added.

.. versionchanged:: 1.14

  The attributes ``answers.question_identifier`` and ``answers.option_identifiers`` have been added.


Order endpoints
---------------

.. versionchanged:: 1.15

   Filtering for emails or order codes is now case-insensitive.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/

   Returns a list of all orders within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orders/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json
      X-Page-Generated: 2017-12-01T10:00:00Z

      {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
          {
            "code": "ABC12",
            "status": "p",
            "secret": "k24fiuwvu8kxz3y1",
            "email": "tester@example.org",
            "locale": "en",
            "datetime": "2017-12-01T10:00:00Z",
            "expires": "2017-12-10T10:00:00Z",
            "last_modified": "2017-12-01T10:00:00Z",
            "payment_date": "2017-12-05",
            "payment_provider": "banktransfer",
            "fees": [],
            "total": "23.00",
            "comment": "",
            "checkin_attention": false,
            "invoice_address": {
                "last_modified": "2017-12-01T10:00:00Z",
                "is_business": True,
                "company": "Sample company",
                "name": "John Doe",
                "street": "Test street 12",
                "zipcode": "12345",
                "city": "Testington",
                "country": "Testikistan",
                "internal_reference": "",
                "vat_id": "EU123456789",
                "vat_id_validated": False
            },
            "positions": [
              {
                "id": 23442,
                "order": "ABC12",
                "positionid": 1,
                "item": 1345,
                "variation": null,
                "price": "23.00",
                "attendee_name": "Peter",
                "attendee_email": null,
                "voucher": null,
                "tax_rate": "0.00",
                "tax_value": "0.00",
                "tax_rule": null,
                "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
                "addon_to": null,
                "subevent": null,
                "checkins": [
                  {
                    "list": 44,
                    "datetime": "2017-12-25T12:45:23Z"
                  }
                ],
                "answers": [
                  {
                    "question": 12,
                    "question_identifier": "WY3TP9SL",
                    "answer": "Foo",
                    "option_idenfiters": [],
                    "options": []
                  }
                ],
                "downloads": [
                  {
                    "output": "pdf",
                    "url": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/download/pdf/"
                  }
                ]
              }
            ],
            "downloads": [
              {
                "output": "pdf",
                "url": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/download/pdf/"
              }
            ]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``datetime``, ``code`` and
                           ``status``. Default: ``datetime``
   :query string code: Only return orders that match the given order code
   :query string status: Only return orders in the given order status (see above)
   :query string email: Only return orders created with the given email address
   :query string locale: Only return orders with the given customer locale
   :query datetime modified_since: Only return orders that have changed since the given date
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :resheader X-Page-Generated: The server time at the beginning of the operation. If you're using this API to fetch
                                differences, this is the value you want to use as ``modified_since`` in your next call.
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/

   Returns information on one order, identified by its order code.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "code": "ABC12",
        "status": "p",
        "secret": "k24fiuwvu8kxz3y1",
        "email": "tester@example.org",
        "locale": "en",
        "datetime": "2017-12-01T10:00:00Z",
        "expires": "2017-12-10T10:00:00Z",
        "last_modified": "2017-12-01T10:00:00Z",
        "payment_date": "2017-12-05",
        "payment_provider": "banktransfer",
        "fees": [],
        "total": "23.00",
        "comment": "",
        "checkin_attention": false,
        "invoice_address": {
            "last_modified": "2017-12-01T10:00:00Z",
            "company": "Sample company",
            "is_business": True,
            "name": "John Doe",
            "street": "Test street 12",
            "zipcode": "12345",
            "city": "Testington",
            "country": "Testikistan",
            "internal_reference": "",
            "vat_id": "EU123456789",
            "vat_id_validated": False
        },
        "positions": [
          {
            "id": 23442,
            "order": "ABC12",
            "positionid": 1,
            "item": 1345,
            "variation": null,
            "price": "23.00",
            "attendee_name": "Peter",
            "attendee_email": null,
            "voucher": null,
            "tax_rate": "0.00",
            "tax_rule": null,
            "tax_value": "0.00",
            "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            "addon_to": null,
            "subevent": null,
            "checkins": [
              {
                "list": 44,
                "datetime": "2017-12-25T12:45:23Z"
              }
            ],
            "answers": [
              {
                "question": 12,
                "question_identifier": "WY3TP9SL",
                "answer": "Foo",
                "option_idenfiters": [],
                "options": []
              }
            ],
            "downloads": [
              {
                "output": "pdf",
                "url": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/download/pdf/"
              }
            ]
          }
        ],
        "downloads": [
          {
            "output": "pdf",
            "url": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/download/pdf/"
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/download/(output)/

   Download tickets for an order, identified by its order code. Depending on the chosen output, the response might
   be a ZIP file, PDF file or something else. The order details response contains a list of output options for this
   particular order.

   Tickets can be only downloaded if the order is paid and if ticket downloads are active. Note that in some cases the
   ticket file might not yet have been created. In that case, you will receive a status code :http:statuscode:`409` and
   you are expected to retry the request after a short period of waiting.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/download/pdf/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/pdf

      ...

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param output: The internal name of the output provider to use
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource
                    **or** downloads are not available for this order at this time. The response content will
                    contain more details.
   :statuscode 404: The requested order or output provider does not exist.
   :statuscode 409: The file is not yet ready and will now be prepared. Retry the request after waiting for a few
                          seconds.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/

   Creates a new order.

   .. warning:: This endpoint is considered **experimental**. It might change at any time without prior notice.

   .. warning::

       This endpoint is intended for advanced users. It is not designed to be used to build your own shop frontend,
       it's rather intended to import attendees from external sources etc.
       There is a lot that it does not or can not do, and you will need to be careful using it.
       It allows to bypass many of the restrictions imposed when creating an order through the
       regular shop.

       Specifically, this endpoint currently

       * does not validate if products are only to be sold in a specific time frame

       * does not validate if the event's ticket sales are already over or haven't started

       * does not validate the number of items per order or the number of times an item can be included in an order

       * does not validate any requirements related to add-on products

       * does not check or calculate prices but believes any prices you send

       * does not support the redemption of vouchers

       * does not prevent you from buying items that can only be bought with a voucher

       * does not calculate fees

       * does not allow to pass data to plugins and will therefore cause issues with some plugins like the shipping
         module

       * does not send order confirmations via email

       * does not support reverse charge taxation

       * does not support file upload questions

   You can supply the following fields of the resource:

   * ``code`` (optional)
   * ``status`` (optional) – Defaults to pending for non-free orders and paid for free orders. You can only set this to
     ``"n"`` for pending or ``"p"`` for paid. If you create a paid order, the ``order_paid`` signal will **not** be
     sent out to plugins and no email will be sent. If you want that behavior, create an unpaid order and then call
     the ``mark_paid`` API method.
   * ``email``
   * ``locale``
   * ``payment_provider`` – The identifier of the payment provider set for this order. This needs to be an existing
     payment provider. You should use ``"free"`` for free orders.
   * ``payment_info`` (optional) – You can pass a nested JSON object that will be set as the internal ``payment_info``
     value of the order. How this value is handled is up to the payment provider and you should only use this if you
     know the specific payment provider in detail. Please keep in mind that the payment provider will not be called
     to do anything about this (i.e. if you pass a bank account to a debit provider, *no* charge will be created),
     this is just informative in case you *handled the payment already*.
   * ``comment`` (optional)
   * ``checkin_attention`` (optional)
   * ``invoice_address`` (optional)

      * ``company``
      * ``is_business``
      * ``name``
      * ``street``
      * ``zipcode``
      * ``city``
      * ``country``
      * ``internal_reference``
      * ``vat_id``

   * ``positions``

      * ``positionid`` (optional, see below)
      * ``item``
      * ``variation``
      * ``price``
      * ``attendee_name``
      * ``attendee_email``
      * ``secret`` (optional)
      * ``addon_to`` (optional, see below)
      * ``subevent``
      * ``answers``

        * ``question``
        * ``answer``
        * ``options``

   * ``fees``

      * ``fee_type``
      * ``value``
      * ``description``
      * ``internal_type``
      * ``tax_rule``

   If you want to use add-on products, you need to set the ``positionid`` fields of all positions manually
   to incrementing integers starting with ``1``. Then, you can reference one of these
   IDs in the ``addon_to`` field of another position. Note that all add_ons for a specific position need to come
   immediately after the position itself.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "email": "dummy@example.org",
        "locale": "en",
        "fees": [
          {
            "fee_type": "payment",
            "value": "0.25",
            "description": "",
            "internal_type": "",
            "tax_rule": 2
          }
        ],
        "payment_provider": "banktransfer",
        "invoice_address": {
          "is_business": False,
          "company": "Sample company",
          "name": "John Doe",
          "street": "Sesam Street 12",
          "zipcode": "12345",
          "city": "Sample City",
          "country": "UK",
          "internal_reference": "",
          "vat_id": ""
        },
        "positions": [
          {
            "positionid": 1,
            "item": 1,
            "variation": None,
            "price": "23.00",
            "attendee_name": "Peter",
            "attendee_email": None,
            "addon_to": None,
            "answers": [
              {
                "question": 1,
                "answer": "23",
                "options": []
              }
            ],
            "subevent": None
          }
        ],
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      (Full order resource, see above.)

   :param organizer: The ``slug`` field of the organizer of the event to create an item for
   :param event: The ``slug`` field of the event to create an item for
   :statuscode 201: no error
   :statuscode 400: The item could not be created due to invalid submitted data or lack of quota.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this
         order.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/mark_paid/

   Marks a pending or expired order as successfully paid.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/mark_paid/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "code": "ABC12",
        "status": "p",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to modify
   :statuscode 200: no error
   :statuscode 400: The order cannot be marked as paid, either because the current order status does not allow it or because no quota is left to perform the operation.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.
   :statuscode 409: The server was unable to acquire a lock and could not process your request. You can try again after a short waiting period.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/mark_canceled/

   Marks a pending order as canceled.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/mark_canceled/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: text/json

      {
          "send_email": true
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "code": "ABC12",
        "status": "c",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to modify
   :statuscode 200: no error
   :statuscode 400: The order cannot be marked as canceled since the current order status does not allow it.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/mark_pending/

   Marks a paid order as unpaid.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/mark_pending/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "code": "ABC12",
        "status": "n",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to modify
   :statuscode 200: no error
   :statuscode 400: The order cannot be marked as unpaid since the current order status does not allow it.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/mark_expired/

   Marks a unpaid order as expired.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/mark_expired/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "code": "ABC12",
        "status": "e",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to modify
   :statuscode 200: no error
   :statuscode 400: The order cannot be marked as expired since the current order status does not allow it.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/extend/

   Extends the payment deadline of a pending order. If the order is already expired and quota is still
   available, its state will be changed to pending.

   The only required parameter of this operation is ``expires``, which should contain a date in the future.
   Note that only a date is expected, not a datetime, since pretix will always set the deadline to the end of the
   day in the event's timezone.

   You can pass the optional parameter ``force``. If it is set to ``true``, the operation will be performed even if
   it leads to an overbooked quota because the order was expired and the tickets have been sold again.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/extend/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: text/json

      {
          "expires": "2017-10-28",
          "force": false
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "code": "ABC12",
        "status": "n",
        "expires": "2017-10-28T23:59:59Z",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to modify
   :statuscode 200: no error
   :statuscode 400: The order cannot be extended since the current order status does not allow it or no quota is available or the submitted date is invalid.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.


Order position endpoints
------------------------

.. versionchanged:: 1.15

   The order positions endpoint has been extended by the filter queries ``item__in``, ``variation__in``,
   ``order__status__in``, ``subevent__in``, ``addon_to__in`` and ``search``. The search for attendee names and order
   codes is now case-insensitive.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orderpositions/

   Returns a list of all order positions within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orderpositions/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
          {
            "id": 23442,
            "order": "ABC12",
            "positionid": 1,
            "item": 1345,
            "variation": null,
            "price": "23.00",
            "attendee_name": "Peter",
            "attendee_email": null,
            "voucher": null,
            "tax_rate": "0.00",
            "tax_rule": null,
            "tax_value": "0.00",
            "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            "addon_to": null,
            "subevent": null,
            "checkins": [
              {
                "list": 44,
                "datetime": "2017-12-25T12:45:23Z"
              }
            ],
            "answers": [
              {
                "question": 12,
                "question_identifier": "WY3TP9SL",
                "answer": "Foo",
                "option_idenfiters": [],
                "options": []
              }
            ],
            "downloads": [
              {
                "output": "pdf",
                "url": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/download/pdf/"
              }
            ]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``order__code``,
                           ``order__datetime``, ``positionid``, ``attendee_name``, and ``order__status``. Default:
                           ``order__datetime,positionid``
   :query string order: Only return positions of the order with the given order code
   :query string search: Fuzzy search matching the attendee name, order code, invoice address name as well as to the beginning of the secret.
   :query integer item: Only return positions with the purchased item matching the given ID.
   :query integer item__in: Only return positions with the purchased item matching one of the given comma-separated IDs.
   :query integer variation: Only return positions with the purchased item variation matching the given ID.
   :query integer variation__in: Only return positions with one of the purchased item variation matching the given
                                 comma-separated IDs.
   :query string attendee_name: Only return positions with the given value in the attendee_name field. Also, add-on
                                products positions are shown if they refer to an attendee with the given name.
   :query string secret: Only return positions with the given ticket secret.
   :query string order__status: Only return positions with the given order status.
   :query string order__status__in: Only return positions with one the given comma-separated order status.
   :query boolean has_checkin: If set to ``true`` or ``false``, only return positions that have or have not been
                               checked in already.
   :query integer subevent: Only return positions of the sub-event with the given ID
   :query integer subevent__in: Only return positions of one of the sub-events with the given comma-separated IDs
   :query integer addon_to: Only return positions that are add-ons to the position with the given ID.
   :query integer addon_to__in: Only return positions that are add-ons to one of the positions with the given
                                comma-separated IDs.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orderpositions/(id)/

   Returns information on one order position, identified by its internal ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 23442,
        "order": "ABC12",
        "positionid": 1,
        "item": 1345,
        "variation": null,
        "price": "23.00",
        "attendee_name": "Peter",
        "attendee_email": null,
        "voucher": null,
        "tax_rate": "0.00",
        "tax_rule": null,
        "tax_value": "0.00",
        "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
        "addon_to": null,
        "subevent": null,
        "checkins": [
          {
            "list": 44,
            "datetime": "2017-12-25T12:45:23Z"
          }
        ],
        "answers": [
          {
            "question": 12,
            "question_identifier": "WY3TP9SL",
            "answer": "Foo",
            "option_idenfiters": [],
            "options": []
          }
        ],
        "downloads": [
          {
            "output": "pdf",
            "url": "https://pretix.eu/api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/download/pdf/"
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the order position to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order position does not exist.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orderpositions/(id)/download/(output)/

   Download tickets for one order position, identified by its internal ID.
   Depending on the chosen output, the response might be a ZIP file, PDF file or something else. The order details
   response contains a list of output options for this particular order position.

   Tickets can be only downloaded if the order is paid and if ticket downloads are active. Also, depending on event
   configuration downloads might be only unavailable for add-on products or non-admission products.
   Note that in some cases the ticket file might not yet have been created. In that case, you will receive a status
   code :http:statuscode:`409` and you are expected to retry the request after a short period of waiting.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/download/pdf/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/pdf

      ...

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the order position to fetch
   :param output: The internal name of the output provider to use
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource
                    **or** downloads are not available for this order position at this time. The response content will
                    contain more details.
   :statuscode 404: The requested order position or download provider does not exist.
   :statuscode 409: The file is not yet ready and will now be prepared. Retry the request after waiting for a few
                    seconds.
