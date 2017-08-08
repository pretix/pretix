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
payment_date                          date                       Date of payment receival
payment_provider                      string                     Payment provider used for this order
payment_fee                           money (string)             Payment fee included in this order's total
payment_fee_tax_rate                  decimal (string)           Tax rate applied to the payment fee
payment_fee_tax_value                 money (string)             Tax value included in the payment fee
payment_fee_tax_rule                  integer                    The ID of the used tax rule (or ``null``)
total                                 money (string)             Total value of this order
comment                               string                     Internal comment on this order
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
├ vat_id                              string                     Customer VAT ID
└ vat_id_validated                    string                     ``True``, if the VAT ID has been validated against the
                                                                 EU VAT service and validation was successful. This only
                                                                 happens in rare cases.
position                              list of objects            List of order positions (see below)
downloads                             list of objects            List of ticket download options for order-wise ticket
                                                                 downloading. This might be a multi-page PDF or a ZIP
                                                                 file of tickets for outputs that do not support
                                                                 multiple tickets natively. See also order position
                                                                 download options.
├ output                              string                     Ticket output provider (e.g. ``pdf``, ``passbook``)
└ url                                 string                     Download URL
===================================== ========================== =======================================================


.. versionchanged:: 1.6

   The ``invoice_address.country`` attribute contains a two-letter country code for all new orders. For old orders,
   a custom text might still be returned.

.. versionchanged:: 1.7

   The attributes ``payment_fee_tax_rule``, ``invoice_address.vat_id_validated`` and ``invoice_address.is_business``
   have been added.


Order position resource
-----------------------

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the order positon
code                                  string                     Order code of the order the position belongs to
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
└ datetime                            datetime                   Time of check-in
downloads                             list of objects            List of ticket download options
├ output                              string                     Ticket output provider (e.g. ``pdf``, ``passbook``)
└ url                                 string                     Download URL
answers                               list of objects            Answers to user-defined questions
├ question                            integer                    Internal ID of the answered question
├ answer                              string                     Text representation of the answer
└ options                             list of integers           Internal IDs of selected option(s)s (only for choice types)
===================================== ========================== =======================================================

.. versionchanged:: 1.7

   The attribute ``tax_rule`` has been added.


Order endpoints
---------------

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
      Content-Type: text/javascript

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
            "payment_date": "2017-12-05",
            "payment_provider": "banktransfer",
            "payment_fee": "0.00",
            "payment_fee_tax_rate": "0.00",
            "payment_fee_tax_value": "0.00",
            "payment_fee_tax_rule": null,
            "total": "23.00",
            "comment": "",
            "invoice_address": {
                "last_modified": "2017-12-01T10:00:00Z",
                "is_business": True,
                "company": "Sample company",
                "name": "John Doe",
                "street": "Test street 12",
                "zipcode": "12345",
                "city": "Testington",
                "country": "Testikistan",
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
                    "datetime": "2017-12-25T12:45:23Z"
                  }
                ],
                "answers": [
                  {
                    "question": 12,
                    "answer": "Foo",
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
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
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
      Content-Type: text/javascript

      {
        "code": "ABC12",
        "status": "p",
        "secret": "k24fiuwvu8kxz3y1",
        "email": "tester@example.org",
        "locale": "en",
        "datetime": "2017-12-01T10:00:00Z",
        "expires": "2017-12-10T10:00:00Z",
        "payment_date": "2017-12-05",
        "payment_provider": "banktransfer",
        "payment_fee": "0.00",
        "payment_fee_tax_rate": "0.00",
        "payment_fee_tax_value": "0.00",
        "payment_fee_tax_rule": null,
        "total": "23.00",
        "comment": "",
        "invoice_address": {
            "last_modified": "2017-12-01T10:00:00Z",
            "company": "Sample company",
            "is_business": True,
            "name": "John Doe",
            "street": "Test street 12",
            "zipcode": "12345",
            "city": "Testington",
            "country": "Testikistan",
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
                "datetime": "2017-12-25T12:45:23Z"
              }
            ],
            "answers": [
              {
                "question": 12,
                "answer": "Foo",
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

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/download/(output)/

   Download tickets for an order, identified by its order code. Depending on the chosen output, the response might
   be a ZIP file, PDF file or something else. The order details response contains a list of output options for this
   partictular order.

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
                    **or** downlodas are not available for this order at this time. The response content will
                    contain more details.
   :statuscode 409: The file is not yet ready and will now be prepared. Retry the request after waiting vor a few
                          seconds.


Order position endpoints
------------------------

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
      Content-Type: text/javascript

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
                "datetime": "2017-12-25T12:45:23Z"
              }
            ],
            "answers": [
              {
                "question": 12,
                "answer": "Foo",
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
   :query integer item: Only return positions with the purchased item matching the given ID.
   :query integer variation: Only return positions with the purchased item variation matching the given ID.
   :query string attendee_name: Only return positions with the given value in the attendee_name field. Also, add-on
                                products positions are shown if they refer to an attendee with the given name.
   :query string secret: Only return positions with the given ticket secret.
   :query string order__status: Only return positions with the given order status.
   :query bollean has_checkin: If set to ``true`` or ``false``, only return positions that have or have not been
                               checked in already.
   :query integer subevent: Only return positions of the sub-event with the given ID
   :query integer addon_to: Only return positions that are add-ons to the position with the given ID.
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
      Content-Type: text/javascript

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
            "datetime": "2017-12-25T12:45:23Z"
          }
        ],
        "answers": [
          {
            "question": 12,
            "answer": "Foo",
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

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orderpositions/(id)/download/(output)/

   Download tickets for one order position, identified by its internal ID.
   Depending on the chosen output, the response might be a ZIP file, PDF file or something else. The order details
   response contains a list of output options for this partictular order position.

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
                    **or** downlodas are not available for this order position at this time. The response content will
                    contain more details.
   :statuscode 409: The file is not yet ready and will now be prepared. Retry the request after waiting vor a few
                    seconds.
