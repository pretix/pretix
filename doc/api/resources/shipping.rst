Shipping
========

.. note:: This API is only available when the plugin **pretix-shipping** is installed (pretix Hosted and Enterprise only).

The shipping plugin provides a HTTP API that exposes the various layouts used to generate PDF badges.

Shipping address resource
-------------------------

The shipping address resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
company                               string                     Customer company name
name                                  string                     Customer name
street                                string                     Customer street
zipcode                               string                     Customer ZIP code
city                                  string                     Customer city
country                               string                     Customer country code
state                                 string                     Customer state (ISO 3166-2 code). Only supported in
                                                                 AU, BR, CA, CN, MY, MX, and US.
gift                                  boolean                    Request by customer to not disclose prices in the shipping
===================================== ========================== =======================================================

Shipping status resource
------------------------

The shipping status resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
method                                integer                    Internal ID of shipping method
status                                string                     Status, one of ``"new"`` or ``"shipped"``
method_type                           string                     Method type, one of ``"ship"``, ``"online"``, or ``"collect"``
===================================== ========================== =======================================================

Print job resource
------------------

The print job resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
code                                  string                     Order code of the ticket order
event                                 string                     Event slug
status                                string                     Status, one of ``"new"`` or ``"shipped"``
method                                string                     Method type, one of ``"ship"``, ``"online"``, or ``"collect"``
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/shippingaddress/

   Returns the shipping address of an order

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/orders/ABC12/shippingaddress/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "company": "ACME Corp",
        "name": "John Doe",
        "street": "Sesame Street 12\nAp. 5",
        "zipcode": "12345",
        "city": "Berlin",
        "country": "DE",
        "state": "",
        "gift": false
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :param order: The ``code`` field of a valid order
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.
   :statuscode 404: The order does not exist or no shipping address is attached.


.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orders/(code)/shippingaddress/

   Returns the shipping status of an order

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/orders/ABC12/shippingstatus/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "method": 23,
        "method_type": "ship",
        "status": "new"
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :param order: The ``code`` field of a valid order
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.
   :statuscode 404: The order does not exist or no shipping address is attached.

.. http:get:: /api/v1/organizers/(organizer)/printjobs/

   Returns a list of ticket orders, only useful with some query filters

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/printjobs/?method=ship&status=new HTTP/1.1
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
            "event": "democon",
            "order": "ABC12",
            "method": "ship",
            "status": "new"
          }
        ]
      }

   :query string method: Filter by response field ``method`` (can be passed multiple times)
   :query string status: Filter by response field ``status``
   :query string event: Filter by response field ``event``
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/printjobs/poll/

   Returns the PDF file for the next job to print.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/printjobs/poll/?method=ship&status=new HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/pdf
      X-Pretix-Order-Code: ABC12

      ...

   :query string method: Filter by response field ``method`` (can be passed multiple times)
   :query string status: Filter by response field ``status``
   :query string event: Filter by response field ``event``
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/printjobs/(order)/ack/

   Change an order's status to "shipped".

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/printjobs/ABC12/ack/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :param order: The ``code`` field of a valid order
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.
   :statuscode 404: The order does not exist.
