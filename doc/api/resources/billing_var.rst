pretix Hosted reseller API
==========================

This API is only accessible to our `value-added reseller partners`_ on pretix Hosted.

.. note:: This API is only accessible with user-level permissions, not with API tokens. Therefore, you will need to
          create an :ref:`OAuth application <rest-oauth>` and obtain an OAuth access token for a user account that has
          permission to your reseller account.

Reseller account resource
-------------------------

The resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Your reseller ID
name                                  string                     Internal name of your reseller account
public_name                           string                     Public name of your reseller account
public_url                            string                     Public URL of your company
support_email                         string                     Your support email address
support_phone                         string                     Your support phone number
communication_language                string                     Language code we use to communicate with you
===================================== ========================== =======================================================


Endpoints
---------

.. http:get:: /api/v1/var/

   Returns a list of all reseller accounts you have access to.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/var/ HTTP/1.1
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
            "id": 1,
            "name": "ticketshop.live Ltd & Co. KG",
            "public_name": "ticketshop.live",
            "public_url": "https://ticketshop.live",
            "support_email": "support@ticketshop.live",
            "support_phone": "+4962213217750",
            "communication_language": "de"
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :statuscode 200: no error
   :statuscode 401: Authentication failure

.. http:get:: /api/v1/var/(id)/

   Returns information on one reseller account, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/var/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "ticketshop.live Ltd & Co. KG",
        "public_name": "ticketshop.live",
        "public_url": "https://ticketshop.live",
        "support_email": "support@ticketshop.live",
        "support_phone": "+4962213217750",
        "communication_language": "de"
      }

   :param id: The ``id`` field of the reseller account to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 404: The requested account does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/var/(id)/create_organizer/

   Creates a new organizer account that will be associated with a given reseller acocunt.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/var/1/create_organizer/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 123

      {
        "name": "My new client",
        "slug": "New client"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "My new client",
        "slug": "New client"
      }

   :param id: The ``id`` field of the reseller account to fetch
   :statuscode 201: no error
   :statuscode 400: Invalid request body, usually the slug is invalid or already taken.
   :statuscode 401: Authentication failure
   :statuscode 404: The requested account does not exist **or** you have no permission to view this resource.

.. _value-added reseller partners: https://pretix.eu/about/en/var
