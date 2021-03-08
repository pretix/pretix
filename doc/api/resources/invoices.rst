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
invoice_from_name                     string                     Sender address: Name
invoice_from                          string                     Sender address: Address lines
invoice_from_zipcode                  string                     Sender address: ZIP code
invoice_from_city                     string                     Sender address: City
invoice_from_country                  string                     Sender address: Country code
invoice_from_tax_id                   string                     Sender address: Local Tax ID
invoice_from_vat_id                   string                     Sender address: EU VAT ID
invoice_to                            string                     Full recipient address
invoice_to_company                    string                     Recipient address: Company name
invoice_to_name                       string                     Recipient address: Person name
invoice_to_street                     string                     Recipient address: Address lines
invoice_to_zipcode                    string                     Recipient address: ZIP code
invoice_to_city                       string                     Recipient address: City
invoice_to_state                      string                     Recipient address: State (only used in some countries)
invoice_to_country                    string                     Recipient address: Country code
invoice_to_vat_id                     string                     Recipient address: EU VAT ID
invoice_to_beneficiary                string                     Invoice beneficiary
custom_field                          string                     Custom invoice address field
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
├ position                            integer                    Number of the line within an invoice.
├ description                         string                     Text representing the invoice line (e.g. product name)
├ item                                integer                    Product used to create this line. Note that everything
                                                                 about the product might have changed since the creation
                                                                 of the invoice. Can be ``null`` for all invoice lines
                                                                 created before this field was introduced as well as for
                                                                 all lines not created by a product (e.g. a shipping or
                                                                 cancellation fee).
├ variation                           integer                    Product variation used to create this line. Note that everything
                                                                 about the product might have changed since the creation
                                                                 of the invoice. Can be ``null`` for all invoice lines
                                                                 created before this field was introduced as well as for
                                                                 all lines not created by a product (e.g. a shipping or
                                                                 cancellation fee).
├ event_date_from                     datetime                   Start date of the (sub)event this line was created for as it
                                                                 was set during invoice creation. Can be ``null`` for all invoice
                                                                 lines created before this was introduced as well as for lines in
                                                                 an event series not created by a product (e.g. shipping or
                                                                 cancellation fees).
├ event_date_to                       datetime                   End date of the (sub)event this line was created for as it
                                                                 was set during invoice creation. Can be ``null`` for all invoice
                                                                 lines created before this was introduced as well as for lines in
                                                                 an event series not created by a product (e.g. shipping or
                                                                 cancellation fees) as well as whenever the respective (sub)event
                                                                 has no end date set.
├ attendee_name                       string                     Attendee name at time of invoice creation. Can be ``null`` if no
                                                                 name was set or if names are configured to not be added to invoices.
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


.. versionchanged:: 3.4

   The attribute ``lines.number`` has been added.

.. versionchanged:: 3.17

   The attribute ``invoice_to_*``, ``invoice_from_*``, ``custom_field``, ``lines.item``, ``lines.variation``, ``lines.event_date_from``,
   ``lines.event_date_to``, and ``lines.attendee_name`` have been added.
   ``refers`` now returns an invoice number including the prefix.


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
            "invoice_from_name": "Big Events LLC",
            "invoice_from": "Demo street 12",
            "invoice_from_zipcode":"",
            "invoice_from_city":"Demo town",
            "invoice_from_country":"US",
            "invoice_from_tax_id":"",
            "invoice_from_vat_id":"",
            "invoice_to": "Sample company\nJohn Doe\nTest street 12\n12345 Testington\nTestikistan\nVAT-ID: EU123456789",
            "invoice_to_company": "Sample company",
            "invoice_to_name": "John Doe",
            "invoice_to_street": "Test street 12",
            "invoice_to_zipcode": "12345",
            "invoice_to_city": "Testington",
            "invoice_to_state": null,
            "invoice_to_country": "TE",
            "invoice_to_vat_id": "EU123456789",
            "invoice_to_beneficiary": "",
            "custom_field": null,
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
                "position": 1,
                "description": "Budget Ticket",
                "item": 1234,
                "variation": 245,
                "event_date_from": "2017-12-27T10:00:00Z",
                "event_date_to": null,
                "attendee_name": null,
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
        "invoice_from_name": "Big Events LLC",
        "invoice_from": "Demo street 12",
        "invoice_from_zipcode":"",
        "invoice_from_city":"Demo town",
        "invoice_from_country":"US",
        "invoice_from_tax_id":"",
        "invoice_from_vat_id":"",
        "invoice_to": "Sample company\nJohn Doe\nTest street 12\n12345 Testington\nTestikistan\nVAT-ID: EU123456789",
        "invoice_to_company": "Sample company",
        "invoice_to_name": "John Doe",
        "invoice_to_street": "Test street 12",
        "invoice_to_zipcode": "12345",
        "invoice_to_city": "Testington",
        "invoice_to_state": null,
        "invoice_to_country": "TE",
        "invoice_to_vat_id": "EU123456789",
        "invoice_to_beneficiary": "",
        "custom_field": null,
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
            "position": 1,
            "description": "Budget Ticket",
            "item": 1234,
            "variation": 245,
            "event_date_from": "2017-12-27T10:00:00Z",
            "event_date_to": null,
            "attendee_name": null,
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
