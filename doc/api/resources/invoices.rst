Invoices
========

Resource description
--------------------

The invoice resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
number                                string                     Invoice number (with prefix)
order                                 string                     Order code of the order this invoice belongs to
is_cancellation                       boolean                    ``true``, if this invoice is the cancellation of a
                                                                 different invoice.
invoice_from                          string                     Sender address
invoice_to                            string                     Receiver address
date                                  date                       Invoice date
refers                                string                     Invoice number of an invoice this invoice refers to
                                                                 (for example a cancellation refers to the invoice it
                                                                 cancels) or ``null``.
locale                                string                     Invoice locale
introductory_text                     string                     Text to be printed above the product list
additional_text                       string                     Text to be printed below the product list
payment_provider_text                 string                     Text to be printed below the product list with
                                                                 payment information
footer_text                           string                     Text to be printed in the page footer area
lines                                 list of objects            The actual invoice contents
├ description                         string                     Text representing the invoice line (e.g. product name)
├ gross_value                         money (string)             Price including taxes
├ tax_value                           money (string)             Tax amount included
├ tax_name                            string                     Name of used tax rate (e.g. "VAT")
└ tax_rate                            decimal (string)           Used tax rate
foreign_currency_display              string                     If the invoice should also show the total and tax
                                                                 amount in a different currency, this contains the
                                                                 currency code (``null`` otherwise).
foreign_currency_rate                 decimal (string)           If ``foreign_currency_rate`` is set and the system
                                                                 knows the exchange rate to the event currency at
                                                                 invoicing time, it is stored here.
foreign_currency_rate_date            date                       If ``foreign_currency_rate`` is set, this signifies the
                                                                 date at which the currency rate was obtained.
internal_reference                    string                     Customer's reference to be printed on the invoice.
===================================== ========================== =======================================================


.. versionchanged:: 1.6

   The attribute ``invoice_no`` has been dropped in favor of ``number`` which includes the number including the prefix,
   since the prefix can now vary. Also, invoices now need to be identified by their ``number`` instead of the raw
   number.


.. versionchanged:: 1.7

   The attributes ``lines.tax_name``, ``foreign_currency_display``, ``foreign_currency_rate``, and
   ``foreign_currency_rate_date`` have been added.


.. versionchanged:: 1.9

   The attribute ``internal_reference`` has been added.


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/invoices/

   Returns a list of all invoices within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/invoices/ HTTP/1.1
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
            "number": "SAMPLECONF-00001",
            "order": "ABC12",
            "is_cancellation": false,
            "invoice_from": "Big Events LLC\nDemo street 12\nDemo town",
            "invoice_to": "Sample company\nJohn Doe\nTest street 12\n12345 Testington\nTestikistan\nVAT ID: EU123456789",
            "date": "2017-12-01",
            "refers": null,
            "locale": "en",
            "introductory_text": "thank you for your purchase of the following items:",
            "internal_reference": "",
            "additional_text": "We are looking forward to see you on our conference!",
            "payment_provider_text": "Please transfer the money to our account ABC…",
            "footer_text": "Big Events LLC - Registration No. 123456 - VAT ID: EU0987654321",
            "lines": [
              {
                "description": "Budget Ticket",
                "gross_value": "23.00",
                "tax_value": "0.00",
                "tax_name": "VAT",
                "tax_rate": "0.00"
              }
            ],
            "foreign_currency_display": "PLN",
            "foreign_currency_rate": "4.2408",
            "foreign_currency_rate_date": "2017-07-24"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query boolean is_cancellation: If set to ``true`` or ``false``, only invoices with this value for the field
                                   ``is_cancellation`` will be returned.
   :query string order: If set, only invoices belonging to the order with the given order code will be returned.
   :query string refers: If set, only invoices referring to the given invoice will be returned.
   :query string locale: If set, only invoices with the given locale will be returned.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``date`` and
                           ``nr`` (equals to ``number``). Default: ``nr``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/invoices/(number)/

   Returns information on one invoice, identified by its invoice number.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/invoices/SAMPLECONF-00001/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "number": "SAMPLECONF-00001",
        "order": "ABC12",
        "is_cancellation": false,
        "invoice_from": "Big Events LLC\nDemo street 12\nDemo town",
        "invoice_to": "Sample company\nJohn Doe\nTest street 12\n12345 Testington\nTestikistan\nVAT ID: EU123456789",
        "date": "2017-12-01",
        "refers": null,
        "locale": "en",
        "introductory_text": "thank you for your purchase of the following items:",
        "internal_reference": "",
        "additional_text": "We are looking forward to see you on our conference!",
        "payment_provider_text": "Please transfer the money to our account ABC…",
        "footer_text": "Big Events LLC - Registration No. 123456 - VAT ID: EU0987654321",
        "lines": [
          {
            "description": "Budget Ticket",
            "gross_value": "23.00",
            "tax_value": "0.00",
            "tax_name": "VAT",
            "tax_rate": "0.00"
          }
        ],
        "foreign_currency_display": "PLN",
        "foreign_currency_rate": "4.2408",
        "foreign_currency_rate_date": "2017-07-24"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param invoice_no: The ``invoice_no`` field of the invoice to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/invoices/(invoice_no)/download/

   Download an invoice in PDF format.

   Note that in some cases the PDF file might not yet have been created. In that case, you will receive a status
   code :http:statuscode:`409` and you are expected to retry the request after a short period of waiting.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/invoices/00001/download/ HTTP/1.1
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
   :param invoice_no: The ``invoice_no`` field of the invoice to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 409: The file is not yet ready and will now be prepared. Retry the request after waiting for a few
                    seconds.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/invoices/(invoice_no)/reissue/

   Cancels the invoice and creates a new one.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/invoices/00001/reissue/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept
      Content-Type: application/pdf

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param invoice_no: The ``invoice_no`` field of the invoice to reissue
   :statuscode 200: no error
   :statuscode 400: The invoice has already been canceled
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/invoices/(invoice_no)/regenerate/

   Re-generates the invoice from order data.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/invoices/00001/regenerate/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept
      Content-Type: application/pdf

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param invoice_no: The ``invoice_no`` field of the invoice to regenerate
   :statuscode 200: no error
   :statuscode 400: The invoice has already been canceled
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.
