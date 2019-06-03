pretix Hosted billing invoices
==============================

This endpoint allows you to access invoices you received for pretix Hosted. It only contains invoices created starting
November 2017.

.. note:: Only available on pretix Hosted, not on self-hosted pretix instances.

Resource description
--------------------

The resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
invoice_number                        string                     Invoice number
date_issued                           date                       Invoice date
===================================== ========================== =======================================================


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/billing_invoices/

   Returns a list of all invoices to a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/billing_invoices/ HTTP/1.1
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
            "invoice_number": "R2019002",
            "date_issued": "2019-06-03"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``date_issued`` and
                           its reverse, ``-date_issued``. Default: ``date_issued``.
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/billing_invoices/(invoice_number)/

   Returns information on one invoice, identified by its invoice number.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/billing_invoices/R2019002/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "invoice_number": "R2019002",
        "date_issued": "2019-06-03"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param invoice_number: The ``invoice_number`` field of the invoice to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/billing_invoices/(invoice_number)/download/

   Download an invoice in PDF format.

   .. warning:: After we created the invoices, they are placed in review with our accounting department. You will
                already see them in the API at this point, but you are not able to download them until they completed
                review and are sent to you via email. This usually takes a few hours. If you try to download them
                in this timeframe, you will receive a status code :http:statuscode:`423`.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/billing_invoices/R2019002/download/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/pdf

      ...

   :param organizer: The ``slug`` field of the organizer to fetch
   :param invoice_number: The ``invoice_number`` field of the invoice to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
   :statuscode 423: The file is not yet ready and will now be prepared. Retry the request after waiting for a few
                    seconds.
