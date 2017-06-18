Orders
======

Order resource
--------------

The order resource contains the following public fields:

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
payment_fee_tax_rate                  decimal (string)           VAT rate applied to the payment fee
payment_fee_tax_value                 money (string)             VAT value included in the payment fee
total                                 money (string)             Total value of this order
comment                               string                     Internal comment on this order
invoice_address                       object                     Invoice address information (can be ``null``)
├ last_modified                       datetime                   Last modification date of the address
├ company                             string                     Customer company name
├ name                                string                     Customer name
├ street                              string                     Customer street
├ zipcode                             string                     Customer ZIP code
├ city                                string                     Customer city
├ country                             string                     Customer country
└ vat_id                              string                     Customer VAT ID
position                              list of objects            List of order positions (see below)
downloads                             list of objects            List of ticket download options for order-wise ticket
                                                                 downloading. This might be a multi-page PDF or a ZIP
                                                                 file of tickets for outputs that do not support
                                                                 multiple tickets natively. See also order position
                                                                 download options.
├ output                              string                     Ticket output provider (e.g. ``pdf``, ``passbook``)
└ url                                 string                     Download URL
===================================== ========================== =======================================================

Order position resource
-----------------------

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
secret                                string                     Secret code printed on the tickets for validation
addon_to                              integer                    Internal ID of the position this position is an add-on for (or ``null``)
checkins                              list of objects            List of check-ins with this ticket
└ datetime                            datetime                   Time of check-in
downloads                             list of objects            List of ticket download options
├ output                              string                     Ticket output provider (e.g. ``pdf``, ``passbook``)
└ url                                 string                     Download URL
===================================== ========================== =======================================================


Endpoints
---------

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
            "id": 1,
            "question": {"en": "T-Shirt size"},
            "type": "C",
            "required": false,
            "items": [1, 2],
            "position": 1,
            "options": [
              {
                "id": 1,
                "answer": {"en": "S"}
              },
              {
                "id": 2,
                "answer": {"en": "M"}
              },
              {
                "id": 3,
                "answer": {"en": "L"}
              }
            ]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id`` and ``position``.
                           Default: ``position``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/questions/(id)/

   Returns information on one question, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/questions/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "question": {"en": "T-Shirt size"},
        "type": "C",
        "required": false,
        "items": [1, 2],
        "position": 1,
        "options": [
          {
            "id": 1,
            "answer": {"en": "S"}
          },
          {
            "id": 2,
            "answer": {"en": "M"}
          },
          {
            "id": 3,
            "answer": {"en": "L"}
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
