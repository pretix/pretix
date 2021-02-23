.. spelling::

   checkins
   pdf


.. _rest-orders:

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
testmode                              boolean                    If ``true``, this order was created when the event was in
                                                                 test mode. Only orders in test mode can be deleted.
secret                                string                     The secret contained in the link sent to the customer
email                                 string                     The customer email address
phone                                 string                     The customer phone number
locale                                string                     The locale used for communication with this customer
sales_channel                         string                     Channel this sale was created through, such as
                                                                 ``"web"``.
datetime                              datetime                   Time of order creation
expires                               datetime                   The order will expire, if it is still pending by this time
payment_date                          date                       **DEPRECATED AND INACCURATE** Date of payment receipt
payment_provider                      string                     **DEPRECATED AND INACCURATE** Payment provider used for this order
total                                 money (string)             Total value of this order
comment                               string                     Internal comment on this order
checkin_attention                     boolean                    If ``true``, the check-in app should show a warning
                                                                 that this ticket requires special attention if a ticket
                                                                 of this order is scanned.
invoice_address                       object                     Invoice address information (can be ``null``)
├ last_modified                       datetime                   Last modification date of the address
├ company                             string                     Customer company name
├ is_business                         boolean                    Business or individual customers (always ``false``
                                                                 for orders created before pretix 1.7, do not rely on
                                                                 it).
├ name                                string                     Customer name
├ name_parts                          object of strings          Customer name decomposition
├ street                              string                     Customer street
├ zipcode                             string                     Customer ZIP code
├ city                                string                     Customer city
├ country                             string                     Customer country code
├ state                               string                     Customer state (ISO 3166-2 code). Only supported in
                                                                 AU, BR, CA, CN, MY, MX, and US.
├ internal_reference                  string                     Customer's internal reference to be printed on the invoice
├ vat_id                              string                     Customer VAT ID
└ vat_id_validated                    string                     ``true``, if the VAT ID has been validated against the
                                                                 EU VAT service and validation was successful. This only
                                                                 happens in rare cases.
positions                             list of objects            List of order positions (see below). By default, only
                                                                 non-canceled positions are included.
fees                                  list of objects            List of fees included in the order total. By default, only
                                                                 non-canceled fees are included.
├ fee_type                            string                     Type of fee (currently ``payment``, ``passbook``,
                                                                 ``other``)
├ value                               money (string)             Fee amount
├ description                         string                     Human-readable string with more details (can be empty)
├ internal_type                       string                     Internal string (i.e. ID of the payment provider),
                                                                 can be empty
├ tax_rate                            decimal (string)           VAT rate applied for this fee
├ tax_value                           money (string)             VAT included in this fee
├ tax_rule                            integer                    The ID of the used tax rule (or ``null``)
└ canceled                            boolean                    Whether or not this fee has been canceled.
downloads                             list of objects            List of ticket download options for order-wise ticket
                                                                 downloading. This might be a multi-page PDF or a ZIP
                                                                 file of tickets for outputs that do not support
                                                                 multiple tickets natively. See also order position
                                                                 download options.
├ output                              string                     Ticket output provider (e.g. ``pdf``, ``passbook``)
└ url                                 string                     Download URL
require_approval                      boolean                    If ``true`` and the order is pending, this order
                                                                 needs approval by an organizer before it can
                                                                 continue. If ``true`` and the order is canceled,
                                                                 this order has been denied by the event organizer.
url                                   string                     The full URL to the order confirmation page
payments                              list of objects            List of payment processes (see below)
refunds                               list of objects            List of refund processes (see below)
last_modified                         datetime                   Last modification of this object
===================================== ========================== =======================================================


.. versionchanged:: 3.5

   The ``order.fees.canceled`` attribute has been added.

.. versionchanged:: 3.8

   The ``reactivate`` operation has been added.

.. versionchanged:: 3.10

   The ``search`` query parameter has been added.

.. versionchanged:: 3.11

   The ``exclude`` and ``subevent_after`` query parameter has been added.

.. versionchanged:: 3.13

   The ``subevent_before`` query parameter has been added.

.. versionchanged:: 3.14

   The ``phone`` attribute has been added.


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
canceled                              boolean                    Whether or not this position has been canceled. Note that
                                                                 by default, only non-canceled positions are shown.
item                                  integer                    ID of the purchased item
variation                             integer                    ID of the purchased variation (or ``null``)
price                                 money (string)             Price of this position
attendee_name                         string                     Specified attendee name for this position (or ``null``)
attendee_name_parts                   object of strings          Decomposition of attendee name (i.e. given name, family name)
attendee_email                        string                     Specified attendee email address for this position (or ``null``)
company                               string                     Attendee company name (or ``null``)
street                                string                     Attendee street (or ``null``)
zipcode                               string                     Attendee ZIP code (or ``null``)
city                                  string                     Attendee city (or ``null``)
country                               string                     Attendee country code (or ``null``)
state                                 string                     Attendee state (ISO 3166-2 code). Only supported in
                                                                 AU, BR, CA, CN, MY, MX, and US, otherwise ``null``.
voucher                               integer                    Internal ID of the voucher used for this position (or ``null``)
tax_rate                              decimal (string)           VAT rate applied for this position
tax_value                             money (string)             VAT included in this position
tax_rule                              integer                    The ID of the used tax rule (or ``null``)
secret                                string                     Secret code printed on the tickets for validation
addon_to                              integer                    Internal ID of the position this position is an add-on for (or ``null``)
subevent                              integer                    ID of the date inside an event series this position belongs to (or ``null``).
pseudonymization_id                   string                     A random ID, e.g. for use in lead scanning apps
checkins                              list of objects            List of check-ins with this ticket
├ id                                  integer                    Internal ID of the check-in event
├ list                                integer                    Internal ID of the check-in list
├ datetime                            datetime                   Time of check-in
├ type                                string                     Type of scan (defaults to ``entry``)
└ auto_checked_in                     boolean                    Indicates if this check-in been performed automatically by the system
downloads                             list of objects            List of ticket download options
├ output                              string                     Ticket output provider (e.g. ``pdf``, ``passbook``)
└ url                                 string                     Download URL
answers                               list of objects            Answers to user-defined questions
├ question                            integer                    Internal ID of the answered question
├ answer                              string                     Text representation of the answer (URL if answer is a file)
├ question_identifier                 string                     The question's ``identifier`` field
├ options                             list of integers           Internal IDs of selected option(s)s (only for choice types)
└ option_identifiers                  list of strings            The ``identifier`` fields of the selected option(s)s
seat                                  objects                    The assigned seat. Can be ``null``.
├ id                                  integer                    Internal ID of the seat instance
├ name                                string                     Human-readable seat name
└ seat_guid                           string                     Identifier of the seat within the seating plan
pdf_data                              object                     Data object required for ticket PDF generation. By default,
                                                                 this field is missing. It will be added only if you add the
                                                                 ``pdf_data=true`` query parameter to your request.
===================================== ========================== =======================================================

.. versionchanged:: 3.3

  The ``url`` of a ticket ``download`` can now also return a ``text/uri-list`` instead of a file. See
  :ref:`order-position-ticket-download` for details.

.. versionchanged:: 3.5

  The attribute ``canceled`` has been added.

.. versionchanged:: 3.8

  The attributes ``company``, ``street``, ``zipcode``, ``city``, ``country``, and ``state`` have been added.

.. versionchanged:: 3.9

  The ``checkin.type`` attribute has been added.

.. versionchanged:: 3.16

   Answers to file questions are now returned as an URL.

.. _order-payment-resource:

Order payment resource
----------------------

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
local_id                              integer                    Internal ID of this payment, starts at 1 for every order
state                                 string                     Payment state, one of ``created``, ``pending``, ``confirmed``, ``canceled``, ``pending``, ``failed``, or ``refunded``
amount                                money (string)             Payment amount
created                               datetime                   Date and time of creation of this payment
payment_date                          datetime                   Date and time of completion of this payment (or ``null``)
provider                              string                     Identification string of the payment provider
payment_url                           string                     The URL where an user can continue with the payment (or ``null``)
details                               object                     Payment-specific information. This is a dictionary
                                                                 with various fields that can be different between
                                                                 payment providers, versions, payment states, etc. If
                                                                 you read this field, you always need to be able to
                                                                 deal with situations where values that you expect are
                                                                 missing. Mostly, the field contains various IDs that
                                                                 can be used for matching with other systems. If a
                                                                 payment provider does not implement this feature,
                                                                 the object is empty.
===================================== ========================== =======================================================

.. _order-refund-resource:

Order refund resource
---------------------

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
local_id                              integer                    Internal ID of this payment, starts at 1 for every order
state                                 string                     Payment state, one of ``created``, ``transit``, ``external``, ``canceled``, ``failed``, or ``done``
source                                string                     How this refund has been created, one of ``buyer``, ``admin``, or ``external``
amount                                money (string)             Payment amount
created                               datetime                   Date and time of creation of this payment
comment                               string                     Reason for refund (shown to the customer in some cases, can be ``null``).
execution_date                        datetime                   Date and time of completion of this refund (or ``null``)
provider                              string                     Identification string of the payment provider
===================================== ========================== =======================================================

List of all orders
------------------

.. versionchanged:: 3.5

   The ``include_canceled_positions`` and ``include_canceled_fees`` query parameters have been added.

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
            "testmode": false,
            "secret": "k24fiuwvu8kxz3y1",
            "url": "https://test.pretix.eu/dummy/dummy/order/ABC12/k24fiuwvu8kxz3y1/",
            "email": "tester@example.org",
            "phone": "+491234567",
            "locale": "en",
            "sales_channel": "web",
            "datetime": "2017-12-01T10:00:00Z",
            "expires": "2017-12-10T10:00:00Z",
            "last_modified": "2017-12-01T10:00:00Z",
            "payment_date": "2017-12-05",
            "payment_provider": "banktransfer",
            "fees": [],
            "total": "23.00",
            "comment": "",
            "checkin_attention": false,
            "require_approval": false,
            "invoice_address": {
                "last_modified": "2017-12-01T10:00:00Z",
                "is_business": true,
                "company": "Sample company",
                "name": "John Doe",
                "name_parts": {"full_name": "John Doe"},
                "street": "Test street 12",
                "zipcode": "12345",
                "city": "Testington",
                "country": "DE",
                "state": "",
                "internal_reference": "",
                "vat_id": "EU123456789",
                "vat_id_validated": false
            },
            "positions": [
              {
                "id": 23442,
                "order": "ABC12",
                "positionid": 1,
                "canceled": false,
                "item": 1345,
                "variation": null,
                "price": "23.00",
                "attendee_name": "Peter",
                "attendee_name_parts": {
                  "full_name": "Peter",
                },
                "attendee_email": null,
                "company": "Sample company",
                "street": "Test street 12",
                "zipcode": "12345",
                "city": "Testington",
                "country": "DE",
                "state": null,
                "voucher": null,
                "tax_rate": "0.00",
                "tax_value": "0.00",
                "tax_rule": null,
                "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
                "addon_to": null,
                "subevent": null,
                "pseudonymization_id": "MQLJvANO3B",
                "seat": null,
                "checkins": [
                  {
                    "list": 44,
                    "type": "entry",
                    "datetime": "2017-12-25T12:45:23Z",
                    "auto_checked_in": false
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
            ],
            "payments": [
              {
                "local_id": 1,
                "state": "confirmed",
                "amount": "23.00",
                "created": "2017-12-01T10:00:00Z",
                "payment_date": "2017-12-04T12:13:12Z",
                "payment_url": null,
                "details": {},
                "provider": "banktransfer"
              }
            ],
            "refunds": []
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``datetime``, ``code``,
                           ``last_modified``, and ``status``. Default: ``datetime``
   :query string code: Only return orders that match the given order code
   :query string status: Only return orders in the given order status (see above)
   :query string search: Only return orders matching a given search query
   :query boolean testmode: Only return orders with ``testmode`` set to ``true`` or ``false``
   :query boolean require_approval: If set to ``true`` or ``false``, only categories with this value for the field
                                    ``require_approval`` will be returned.
   :query include_canceled_positions: If set to ``true``, the output will contain canceled order positions. Note that this
                                      only affects position-level cancellations, not fully-canceled orders.
   :query include_canceled_fees: If set to ``true``, the output will contain canceled order fees.
   :query string email: Only return orders created with the given email address
   :query string locale: Only return orders with the given customer locale
   :query datetime modified_since: Only return orders that have changed since the given date. Be careful: We only
       recommend using this in combination with ``testmode=false``, since test mode orders can vanish at any time and
       you will not notice it using this method.
   :query datetime created_since: Only return orders that have been created since the given date.
   :query datetime subevent_after: Only return orders that contain a ticket for a subevent taking place after the given date. This is an exclusive after, and it considers the **end** of the subevent (or its start, if the end is not set).
   :query datetime subevent_before: Only return orders that contain a ticket for a subevent taking place after the given date. This is an exclusive before, and it considers the **start** of the subevent.
   :query string exclude: Exclude a field from the output, e.g. ``fees`` or ``positions.downloads``. Can be used as a performance optimization. Can be passed multiple times.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :resheader X-Page-Generated: The server time at the beginning of the operation. If you're using this API to fetch
                                differences, this is the value you want to use as ``modified_since`` in your next call.
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

Fetching individual orders
--------------------------

.. versionchanged:: 3.5

   The ``include_canceled_positions`` and ``include_canceled_fees`` query parameters have been added.

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
        "testmode": false,
        "secret": "k24fiuwvu8kxz3y1",
        "url": "https://test.pretix.eu/dummy/dummy/order/ABC12/k24fiuwvu8kxz3y1/",
        "email": "tester@example.org",
        "phone": "+491234567",
        "locale": "en",
        "sales_channel": "web",
        "datetime": "2017-12-01T10:00:00Z",
        "expires": "2017-12-10T10:00:00Z",
        "last_modified": "2017-12-01T10:00:00Z",
        "payment_date": "2017-12-05",
        "payment_provider": "banktransfer",
        "fees": [],
        "total": "23.00",
        "comment": "",
        "checkin_attention": false,
        "require_approval": false,
        "invoice_address": {
            "last_modified": "2017-12-01T10:00:00Z",
            "company": "Sample company",
            "is_business": true,
            "name": "John Doe",
            "name_parts": {"full_name": "John Doe"},
            "street": "Test street 12",
            "zipcode": "12345",
            "city": "Testington",
            "country": "DE",
            "state": "",
            "internal_reference": "",
            "vat_id": "EU123456789",
            "vat_id_validated": false
        },
        "positions": [
          {
            "id": 23442,
            "order": "ABC12",
            "positionid": 1,
            "canceled": false,
            "item": 1345,
            "variation": null,
            "price": "23.00",
            "attendee_name": "Peter",
            "attendee_name_parts": {
              "full_name": "Peter",
            },
            "attendee_email": null,
            "company": "Sample company",
            "street": "Test street 12",
            "zipcode": "12345",
            "city": "Testington",
            "country": "DE",
            "state": null,
            "voucher": null,
            "tax_rate": "0.00",
            "tax_rule": null,
            "tax_value": "0.00",
            "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            "addon_to": null,
            "subevent": null,
            "pseudonymization_id": "MQLJvANO3B",
            "seat": null,
            "checkins": [
              {
                "list": 44,
                "type": "entry",
                "datetime": "2017-12-25T12:45:23Z",
                "auto_checked_in": false
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
        ],
        "payments": [
          {
            "local_id": 1,
            "state": "confirmed",
            "amount": "23.00",
            "created": "2017-12-01T10:00:00Z",
            "payment_date": "2017-12-04T12:13:12Z",
            "payment_url": null,
            "details": {},
            "provider": "banktransfer"
          }
        ],
        "refunds": []
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :query include_canceled_positions: If set to ``true``, the output will contain canceled order positions. Note that this
                                      only affects position-level cancellations, not fully-canceled orders.
   :query include_canceled_fees: If set to ``true``, the output will contain canceled order fees.
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

Order ticket download
---------------------

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

Updating order fields
---------------------

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/

   Updates specific fields on an order. Currently, only the following fields are supported:

   * ``email``

   * ``phone``

   * ``checkin_attention``

   * ``locale``

   * ``comment``

   * ``invoice_address`` (you always need to supply the full object, or ``null`` to delete the current address)

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "email": "other@example.org",
        "locale": "de",
        "comment": "Foo",
        "checkin_attention": true
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      (Full order resource, see above.)

   :param organizer: The ``slug`` field of the organizer of the event
   :param event: The ``slug`` field of the event
   :param code: The ``code`` field of the order to update

   :statuscode 200: no error
   :statuscode 400: The order could not be updated due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to update this order.

Generating new secrets
----------------------

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/regenerate_secrets/

   Triggers generation of new ``secret`` attributes for both the order and all order positions.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/regenerate_secrets/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      (Full order resource, see above.)

   :param organizer: The ``slug`` field of the organizer of the event
   :param event: The ``slug`` field of the event
   :param code: The ``code`` field of the order to update

   :statuscode 200: no error
   :statuscode 400: The order could not be updated due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to update this order.

Deleting orders
---------------

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/

   Deletes an order. Works only if the order has ``testmode`` set to ``true``.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept
      Content-Type: application/json

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource **or** the order may not be deleted.
   :statuscode 404: The requested order does not exist.

.. _rest-orders-create:

Creating orders
---------------

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/

   Creates a new order.

   .. warning::

       This endpoint is intended for advanced users. It is not designed to be used to build your own shop frontend,
       it's rather intended to import attendees from external sources etc.
       There is a lot that it does not or can not do, and you will need to be careful using it.
       It allows to bypass many of the restrictions imposed when creating an order through the
       regular shop.

       Specifically, this endpoint currently

       * does not validate if products are only to be sold in a specific time frame

       * does not validate if products are only to be sold on other sales channels

       * does not validate if the event's ticket sales are already over or haven't started

       * does not validate the number of items per order or the number of times an item can be included in an order

       * does not validate any requirements related to add-on products and does not add bundled products automatically

       * does not check prices but believes any prices you send

       * does not prevent you from buying items that can only be bought with a voucher

       * does not calculate fees automatically

       * does not allow to pass data to plugins and will therefore cause issues with some plugins like the shipping
         module

       * does not support file upload questions

       * does not support redeeming gift cards

   You can supply the following fields of the resource:

   * ``code`` (optional)
   * ``status`` (optional) – Defaults to pending for non-free orders and paid for free orders. You can only set this to
     ``"n"`` for pending or ``"p"`` for paid. We will create a payment object for this order either in state ``created``
     or in state ``confirmed``, depending on this value. If you create a paid order, the ``order_paid`` signal will
     **not** be sent out to plugins and no email will be sent. If you want that behavior, create an unpaid order and
     then call the ``mark_paid`` API method.
   * ``testmode`` (optional) – Defaults to ``false``
   * ``consume_carts`` (optional) – A list of cart IDs. All cart positions with these IDs will be deleted if the
     order creation is successful. Any quotas or seats that become free by this operation will be credited to your order
     creation.
   * ``email`` (optional)
   * ``locale``
   * ``sales_channel`` (optional)
   * ``payment_provider`` (optional) – The identifier of the payment provider set for this order. This needs to be an
     existing payment provider. You should use ``"free"`` for free orders, and we strongly advise to use ``"manual"``
     for all orders you create as paid. This field is optional when the order status is ``"n"`` or the order total is
     zero, otherwise it is required.
   * ``payment_info`` (optional) – You can pass a nested JSON object that will be set as the internal ``info``
     value of the payment object that will be created. How this value is handled is up to the payment provider and you
     should only use this if you know the specific payment provider in detail. Please keep in mind that the payment
     provider will not be called to do anything about this (i.e. if you pass a bank account to a debit provider, *no*
     charge will be created), this is just informative in case you *handled the payment already*.
   * ``payment_date`` (optional) – Date and time of the completion of the payment.
   * ``comment`` (optional)
   * ``checkin_attention`` (optional)
   * ``invoice_address`` (optional)

      * ``company``
      * ``is_business``
      * ``name`` **or** ``name_parts``
      * ``street``
      * ``zipcode``
      * ``city``
      * ``country``
      * ``state``
      * ``internal_reference``
      * ``vat_id``
      * ``vat_id_validated`` (optional) – If you need support for reverse charge (rarely the case), you need to check
       yourself if the passed VAT ID is a valid EU VAT ID. In that case, set this to ``true``. Only valid VAT IDs will
       trigger reverse charge taxation. Don't forget to set ``is_business`` as well!

   * ``positions``

      * ``positionid`` (optional, see below)
      * ``item``
      * ``variation`` (optional)
      * ``price`` (optional, if set to ``null`` or missing the price will be computed from the given product)
      * ``seat`` (The ``seat_guid`` attribute of a seat. Required when the specified ``item`` requires a seat, otherwise must be ``null``.)
      * ``attendee_name`` **or** ``attendee_name_parts`` (optional)
      * ``voucher`` (optional, the ``code`` attribute of a valid voucher)
      * ``attendee_email`` (optional)
      * ``company`` (optional)
      * ``street`` (optional)
      * ``zipcode`` (optional)
      * ``city`` (optional)
      * ``country`` (optional)
      * ``state`` (optional)
      * ``secret`` (optional)
      * ``addon_to`` (optional, see below)
      * ``subevent`` (optional)
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
      * ``_treat_value_as_percentage`` (Optional convenience flag. If set to ``true``, your ``value`` parameter will
        be treated as a percentage and the fee will be calculated using that percentage and the sum of all product
        prices. Note that this will not include other fees and is calculated once during order generation and will not
        be respected automatically when the order changes later.)
      * ``_split_taxes_like_products`` (Optional convenience flag. If set to ``true``, your ``tax_rule`` will be ignored
        and the fee will be taxed like the products in the order. If the products have multiple tax rates, multiple fees
        will be generated with weights adjusted to the net price of the products. Note that this will be calculated once
        during order generation and is not respected automatically when the order changes later.)

   * ``force`` (optional). If set to ``true``, quotas will be ignored.
   * ``send_email`` (optional). If set to ``true``, the same emails will be sent as for a regular order, regardless of
     whether these emails are enabled for certain sales channels. Defaults to
     ``false``. Used to be ``send_mail`` before pretix 3.14.

   If you want to use add-on products, you need to set the ``positionid`` fields of all positions manually
   to incrementing integers starting with ``1``. Then, you can reference one of these
   IDs in the ``addon_to`` field of another position. Note that all add_ons for a specific position need to come
   immediately after the position itself.

   Starting with pretix 3.7, you can add ``"simulate": true`` to the body to do a "dry run" of your order. This will
   validate your order and return you an order object with the resulting prices, but will not create an actual order.
   You can use this for testing or to look up prices. In this case, some attributes are ignored, such as whether
   to send an email or what payment provider will be used. Note that some returned fields will contain empty values
   (e.g. all ``id`` fields of positions will be zero) and some will contain fake values (e.g. the order code will
   always be ``PREVIEW``). pretix plugins will not be triggered, so some special behavior might be missing as well.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "email": "dummy@example.org",
        "locale": "en",
        "sales_channel": "web",
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
          "is_business": false,
          "company": "Sample company",
          "name_parts": {"full_name": "John Doe"},
          "street": "Sesam Street 12",
          "zipcode": "12345",
          "city": "Sample City",
          "country": "UK",
          "state": "",
          "internal_reference": "",
          "vat_id": ""
        },
        "positions": [
          {
            "positionid": 1,
            "item": 1,
            "variation": null,
            "price": "23.00",
            "attendee_name_parts": {
              "full_name": "Peter"
            },
            "attendee_email": null,
            "addon_to": null,
            "answers": [
              {
                "question": 1,
                "answer": "23",
                "options": []
              }
            ],
            "subevent": null
          }
        ]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      (Full order resource, see above.)

   :param organizer: The ``slug`` field of the organizer of the event to create an order for
   :param event: The ``slug`` field of the event to create an order for
   :statuscode 201: no error
   :statuscode 400: The order could not be created due to invalid submitted data or lack of quota.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this
         order.

Order state operations
----------------------

.. versionchanged:: 3.12

   The ``mark_paid`` operation now takes a ``send_email`` parameter.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/mark_paid/

   Marks a pending or expired order as successfully paid.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/mark_paid/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

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

   Cancels an order. For a pending order, this will set the order to status ``c``. For a paid order, this will set
   the order to status ``c`` if no ``cancellation_fee`` is passed. If you do pass a ``cancellation_fee``, the order
   will instead stay paid, but all positions will be removed (or marked as canceled) and replaced by the cancellation
   fee as the only component of the order.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/mark_canceled/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: text/json

      {
          "send_email": true,
          "cancellation_fee": null
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

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/reactivate/

   Reactivates a canceled order. This will set the order to pending or paid state. Only possible if all products are
   still available.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/reactivate/ HTTP/1.1
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
   :statuscode 400: The order cannot be reactivated
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

   Marks an unpaid order as expired.

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

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/approve/

   Approve an order that is pending approval.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/approve/ HTTP/1.1
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
        "require_approval": false,
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to modify
   :statuscode 200: no error
   :statuscode 400: The order cannot be approved, likely because the current order status does not allow it.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.
   :statuscode 409: The server was unable to acquire a lock and could not process your request. You can try again after a short waiting period.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/deny/

   Marks an order that is pending approval as denied.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/deny/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: text/json

      {
          "send_email": true,
          "comment": "You're not a business customer!"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "code": "ABC12",
        "status": "c",
        "require_approval": true,
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to modify
   :statuscode 200: no error
   :statuscode 400: The order cannot be marked as denied since the current order status does not allow it.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to update this resource.
   :statuscode 404: The requested order does not exist.

Generating invoices
-------------------

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/create_invoice/

   Creates an invoice for an order which currently does not have an invoice. Returns the
   invoice object.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/create_invoice/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "order": "FOO",
        "number": "DUMMY-00001",
        "is_cancellation": false,
        ...
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to create an invoice for
   :statuscode 200: no error
   :statuscode 400: The invoice can not be created (invoicing disabled, the order already has an invoice, …)
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

Sending e-mails
---------------

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/resend_link/

   Sends an email to the buyer with the link to the order page.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/resend_link/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param code: The ``code`` field of the order to send an email for
   :statuscode 200: no error
   :statuscode 400: The order does not have an email address associated
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.
   :statuscode 503: The email could not be sent.

List of all order positions
---------------------------

.. versionchanged:: 3.5

   The ``include_canceled_positions`` and ``include_canceled_fees`` query parameters have been added.

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
            "canceled": false,
            "item": 1345,
            "variation": null,
            "price": "23.00",
            "attendee_name": "Peter",
            "attendee_name_parts": {
              "full_name": "Peter"
            },
            "attendee_email": null,
            "voucher": null,
            "tax_rate": "0.00",
            "tax_rule": null,
            "tax_value": "0.00",
            "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            "pseudonymization_id": "MQLJvANO3B",
            "seat": null,
            "addon_to": null,
            "subevent": null,
            "checkins": [
              {
                "list": 44,
                "type": "entry",
                "datetime": "2017-12-25T12:45:23Z",
                "auto_checked_in": false
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
   :query string pseudonymization_id: Only return positions with the given pseudonymization ID.
   :query string order__status: Only return positions with the given order status.
   :query string order__status__in: Only return positions with one the given comma-separated order status.
   :query boolean has_checkin: If set to ``true`` or ``false``, only return positions that have or have not been
                               checked in already.
   :query integer subevent: Only return positions of the sub-event with the given ID
   :query integer subevent__in: Only return positions of one of the sub-events with the given comma-separated IDs
   :query integer addon_to: Only return positions that are add-ons to the position with the given ID.
   :query integer addon_to__in: Only return positions that are add-ons to one of the positions with the given
                                comma-separated IDs.
   :query string voucher: Only return positions with a specific voucher.
   :query string voucher__code: Only return positions with a specific voucher code.
   :query include_canceled_positions: If set to ``true``, the output will contain canceled order positions. Note that this
                                      only affects position-level cancellations, not fully-canceled orders.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

Fetching individual positions
-----------------------------

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
        "canceled": false,
        "item": 1345,
        "variation": null,
        "price": "23.00",
        "attendee_name": "Peter",
        "attendee_name_parts": {
          "full_name": "Peter",
        },
        "attendee_email": null,
        "voucher": null,
        "tax_rate": "0.00",
        "tax_rule": null,
        "tax_value": "0.00",
        "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
        "addon_to": null,
        "subevent": null,
        "pseudonymization_id": "MQLJvANO3B",
        "seat": null,
        "checkins": [
          {
            "list": 44,
            "type": "entry",
            "datetime": "2017-12-25T12:45:23Z",
            "auto_checked_in": false
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
   :query include_canceled_positions: If set to ``true``, canceled positions may be returned (otherwise, they return 404).
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order position does not exist.

.. _`order-position-ticket-download`:

Order position ticket download
------------------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orderpositions/(id)/download/(output)/

   Download tickets for one order position, identified by its internal ID.
   Depending on the chosen output, the response might be a ZIP file, PDF file or something else. The order details
   response contains a list of output options for this particular order position.

   Be aware that the output does not have to be a file, but can also be a regular HTTP response with a ``Content-Type``
   set to ``text/uri-list``. In this case, the user is expected to navigate to that URL in order to access their ticket.
   The referenced URL can provide a download or a regular, human-viewable website - so it is advised to open this URL
   in a webbrowser and leave it up to the user to handle the result.

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

Manipulating individual positions
---------------------------------

.. versionchanged:: 3.15

   The ``PATCH`` method has been added for individual positions.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/orderpositions/(id)/

   Updates specific fields on an order position. Currently, only the following fields are supported:

   * ``attendee_email``

   * ``attendee_name_parts`` or ``attendee_name``

   * ``company``

   * ``street``

   * ``zipcode``

   * ``city``

   * ``country``

   * ``state``

   * ``answers``: If specified, you will need to provide **all** answers for this order position.
     Validation is handled the same way as when creating orders through the API. You are therefore
     expected to provide ``question``, ``answer``, and possibly ``options``. ``question_identifier``
     and ``option_identifiers`` will be ignored.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "attendee_email": "other@example.org"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      (Full order resource, see above.)

   :param organizer: The ``slug`` field of the organizer of the event
   :param event: The ``slug`` field of the event
   :param id: The ``id`` field of the order position to update

   :statuscode 200: no error
   :statuscode 400: The order could not be updated due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to update this order.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/orderpositions/(id)/

   Deletes an order position, identified by its internal ID.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the order position to delete
   :statuscode 204: no error
   :statuscode 400: This position cannot be deleted (e.g. last position in order)
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order position does not exist.


Order payment endpoints
-----------------------

.. versionchanged:: 3.6

   Payments can now be created through the API.

.. versionchanged:: 3.12

   The ``confirm`` operation now takes a ``send_email`` parameter.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/payments/

   Returns a list of all payments for an order.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/payments/ HTTP/1.1
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
            "local_id": 1,
            "state": "confirmed",
            "amount": "23.00",
            "created": "2017-12-01T10:00:00Z",
            "payment_date": "2017-12-04T12:13:12Z",
            "payment_url": null,
            "details": {},
            "provider": "banktransfer"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param order: The ``code`` field of the order to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/payments/(local_id)/

   Returns information on one payment, identified by its order-local ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/payments/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "confirmed",
        "amount": "23.00",
        "created": "2017-12-01T10:00:00Z",
        "payment_date": "2017-12-04T12:13:12Z",
        "payment_url": null,
        "details": {},
        "provider": "banktransfer"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param local_id: The ``local_id`` field of the payment to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order or payment does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/payments/(local_id)/confirm/

   Marks a payment as confirmed. Only allowed in states ``pending`` and ``created``.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/payments/1/confirm/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
          "send_email": true,
          "force": false
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "confirmed",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param local_id: The ``local_id`` field of the payment to modify
   :statuscode 200: no error
   :statuscode 400: Invalid request or payment state
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order or payment does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/payments/(local_id)/cancel/

   Marks a payment as canceled. Only allowed in states ``pending`` and ``created``.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/payments/1/cancel/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "canceled",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param local_id: The ``local_id`` field of the payment to modify
   :statuscode 200: no error
   :statuscode 400: Invalid request or payment state
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order or payment does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/payments/(local_id)/refund/

   Create and execute a manual refund. Only available in ``confirmed`` state. Returns a refund resource, not
   a payment resource!

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/payments/1/refund/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "amount": "23.00",
        "mark_canceled": false
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "source": "admin",
        "state": "done",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param local_id: The ``local_id`` field of the payment to modify
   :statuscode 200: no error
   :statuscode 400: Invalid request, payment state, or operation not supported by the payment provider
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order or payment does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/payments/

   Creates a new payment.

   Be careful with the ``info`` parameter: You can pass a nested JSON object that will be set as the internal ``info``
   value of the payment object that will be created. How this value is handled is up to the payment provider and you
   should only use this if you know the specific payment provider in detail. Please keep in mind that the payment
   provider will not be called to do anything about this (i.e. if you pass a bank account to a debit provider, *no*
   charge will be created), this is just informative in case you *handled the payment already*.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/payments/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "state": "confirmed",
        "amount": "23.00",
        "payment_date": "2017-12-04T12:13:12Z",
        "info": {},
        "send_email": false,
        "provider": "banktransfer"
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "confirmed",
        "amount": "23.00",
        "created": "2017-12-01T10:00:00Z",
        "payment_date": "2017-12-04T12:13:12Z",
        "payment_url": null,
        "details": {},
        "provider": "banktransfer"
      }

   :param organizer: The ``slug`` field of the organizer to access
   :param event: The ``slug`` field of the event to access
   :param order: The ``code`` field of the order to access
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.


Order refund endpoints
----------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/refunds/

   Returns a list of all refunds for an order.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/refunds/ HTTP/1.1
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
            "local_id": 1,
            "state": "done",
            "source": "admin",
            "amount": "23.00",
            "payment": 1,
            "created": "2017-12-01T10:00:00Z",
            "execution_date": "2017-12-04T12:13:12Z",
            "comment": "Cancellation",
            "provider": "banktransfer"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param order: The ``code`` field of the order to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/refunds/(local_id)/

   Returns information on one refund, identified by its order-local ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/refunds/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "done",
        "source": "admin",
        "amount": "23.00",
        "payment": 1,
        "created": "2017-12-01T10:00:00Z",
        "execution_date": "2017-12-04T12:13:12Z",
        "comment": "Cancellation",
        "provider": "banktransfer"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param local_id: The ``local_id`` field of the refund to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order or refund does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/refunds/

   Creates a refund manually.

   .. warning:: We recommend to only use this endpoint for refunds with payment provider ``manual``. This endpoint also
                does not check for mismatching amounts etc. Be careful!

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/refunds/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "state": "created",
        "source": "admin",
        "amount": "23.00",
        "payment": 1,
        "execution_date": null,
        "comment": "Cancellation",
        "provider": "manual",
        "mark_canceled": false,
        "mark_pending": true
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "created",
        "source": "admin",
        "amount": "23.00",
        "payment": 1,
        "created": "2017-12-01T10:00:00Z",
        "execution_date": null,
        "comment": "Cancellation",
        "provider": "manual"
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param order: The ``code`` field of the order to fetch
   :statuscode 200: no error
   :statuscode 400: Invalid data supplied
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/refunds/(local_id)/done/

   Marks a refund as completed. Only allowed in states ``transit`` and ``created``.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/refunds/1/done/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "done",
        ....
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param local_id: The ``local_id`` field of the refund to modify
   :statuscode 200: no error
   :statuscode 400: Invalid request or refund state
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order or refund does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/refunds/(local_id)/process/

   Acts on an external refund, either marks the order as canceled or pending. Only allowed in state ``external``.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/refunds/1/done/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {"mark_canceled": false}

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "done",
        ....
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param local_id: The ``local_id`` field of the refund to modify
   :statuscode 200: no error
   :statuscode 400: Invalid request or refund state
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order or refund does not exist.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/refunds/(local_id)/cancel/

   Marks a refund as canceled. Only allowed in states ``transit``, ``external``, and ``created``.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/orders/ABC12/refunds/1/cancel/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "local_id": 1,
        "state": "canceled",
        ....
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param code: The ``code`` field of the order to fetch
   :param local_id: The ``local_id`` field of the refund to modify
   :statuscode 200: no error
   :statuscode 400: Invalid request or refund state
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 404: The requested order or refund does not exist.

Revoked ticket secrets
----------------------

With some non-default ticket secret generation methods, a list of revoked ticket secrets is required for proper validation.

.. versionchanged:: 3.12

   Added revocation lists.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/revokedsecrets/

   Returns a list of all revoked secrets within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/revokedsecrets/ HTTP/1.1
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
            "id": 1234,
            "secret": "k24fiuwvu8kxz3y1",
            "created": "2017-12-01T10:00:00Z",
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``secret`` and ``created``. Default: ``-created``
   :query datetime created_since: Only return revocations that have been created since the given date.
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :resheader X-Page-Generated: The server time at the beginning of the operation. If you're using this API to fetch
                                differences, this is the value you want to use as ``created_since`` in your next call.
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
