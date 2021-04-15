.. _`rest-customers`:

Customers
=========

Resource description
--------------------

The customer resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
identifier                            string                     Internal ID of the customer
email                                 string                     Customer email address
name                                  string                     Name of this customer (or ``null``)
name_parts                            object of strings          Decomposition of name (i.e. given name, family name)
is_active                             boolean                    Whether this account is active
is_verified                           boolean                    Whether the email address of this account has been
                                                                 verified
last_login                            datetime                   Date and time of last login
date_joined                           datetime                   Date and time of registration
locale                                string                     Prefered language of the customer
last_modified                         datetime                   Date and time of modification of the record
===================================== ========================== =======================================================

.. versionadded:: 4.0

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/customers/

   Returns a list of all customers registered with a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/customers/ HTTP/1.1
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
            "identifier": "8WSAJCJ",
            "email": "customer@example.org",
            "name": "John Doe",
            "name_parts": {
                "_scheme": "full",
                "full_name": "John Doe"
            },
            "is_active": true,
            "is_verified": false,
            "last_login": null,
            "date_joined": "2021-04-06T13:44:22.809216Z",
            "locale": "de",
            "last_modified": "2021-04-06T13:44:22.809377Z"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string email: Only fetch customers with this email address
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/customers/(identifier)/

   Returns information on one customer, identified by its identifier.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/customers/8WSAJCJ/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "identifier": "8WSAJCJ",
        "email": "customer@example.org",
        "name": "John Doe",
        "name_parts": {
            "_scheme": "full",
            "full_name": "John Doe"
        },
        "is_active": true,
        "is_verified": false,
        "last_login": null,
        "date_joined": "2021-04-06T13:44:22.809216Z",
        "locale": "de",
        "last_modified": "2021-04-06T13:44:22.809377Z"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param identifier: The ``identifier`` field of the customer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/customers/

   Creates a new customer

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/customers/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "email": "test@example.org"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "identifier": "8WSAJCJ",
        "email": "test@example.org",
        ...
      }

   :param organizer: The ``slug`` field of the organizer to create a customer for
   :statuscode 201: no error
   :statuscode 400: The customer could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/customers/(identifier)/

   Update a customer. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``identifier``, ``last_login``, ``date_joined``, ``name``,
   and ``last_modified`` fields.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/customers/8WSAJCJ/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "email": "test@example.org"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "identifier": "8WSAJCJ",
        "email": "test@example.org",
        …
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param identifier: The ``identifier`` field of the customer to modify
   :statuscode 200: no error
   :statuscode 400: The customer could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:post:: /api/v1/organizers/(organizer)/customers/(identifier)/anonymize/

   Anonymize a customer. Deletes personal data and disconnects from existing orders.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/customers/8WSAJCJ/anonymize/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "identifier": "8WSAJCJ",
        "email": null,
        …
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param identifier: The ``identifier`` field of the customer to modify
   :statuscode 200: no error
   :statuscode 400: The customer could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.
