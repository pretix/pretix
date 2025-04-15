Secrets Import
==============

.. note:: This API is only available when the plugin **pretix-secrets-import** is installed (pretix Hosted and Enterprise only).

Usually, pretix generates ticket secrets (i.e. the QR code used for scanning) itself. You can read more about this
process at :ref:`secret_generators`.

With the "Secrets Import" plugin, you can upload your own list of secrets to be used instead. This is useful for
integrating with third-party check-in systems.


API Resource description
-------------------------

The secrets import plugin provides a HTTP API that allows you to create new secrets.

The imported secret resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the secret
secret                                string                     Actual string content of the secret (QR code content)
used                                  boolean                    Whether the secret was already used for a ticket. If ``true``,
                                                                 the secret can no longer be deleted. Secrets are never used
                                                                 twice, even if an order is canceled or deleted.
item                                  integer                    Internal ID of a product, or ``null``. If set, the secret
                                                                 will only be used for tickets of this product.
variation                             integer                    Internal ID of a product variation, or ``null``. If set, the secret
                                                                 will only be used for tickets of this product variation.
subevent                              integer                    Internal ID of an event series date, or ``null``. If set, the secret
                                                                 will only be used for tickets of this event series date.
===================================== ========================== =======================================================

API Endpoints
-------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/imported_secrets/

   Returns a list of all secrets imported for an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/imported_secrets/ HTTP/1.1
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
            "secret": "foobar",
            "used": false,
            "item": null,
            "variation": null,
            "subevent": null
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/imported_secrets/(id)/

   Returns information on one secret, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/imported_secrets/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "secret": "foobar",
        "used": false,
        "item": null,
        "variation": null,
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the secret to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/secret does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/imported_secrets/

   Create a new secret.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/imported_secrets/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 166

      {
        "secret": "foobar",
        "used": false,
        "item": null,
        "variation": null,
        "subevent": null
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "secret": "foobar",
        "used": false,
        "item": null,
        "variation": null,
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to a create new secret for
   :param event: The ``slug`` field of the event to create a new secret for
   :statuscode 201: no error
   :statuscode 400: The secret could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create secrets.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/imported_secrets/bulk_create/

   Create new secrets in bulk (up to 500 per request). The request either succeeds or fails entirely.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/imported_secrets/bulk_create/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 166

      [
        {
          "secret": "foobar",
          "used": false,
          "item": null,
          "variation": null,
          "subevent": null
        },
        {
          "secret": "baz",
          "used": false,
          "item": null,
          "variation": null,
          "subevent": null
        }
      ]

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      [
        {
          "id": 1,
          "secret": "foobar",
          "used": false,
          "item": null,
          "variation": null,
          "subevent": null
        },
        {
          "id": 2,
          "secret": "baz",
          "used": false,
          "item": null,
          "variation": null,
          "subevent": null
        }
      ]

   :param organizer: The ``slug`` field of the organizer to create new secrets for
   :param event: The ``slug`` field of the event to create new secrets for
   :statuscode 201: no error
   :statuscode 400: The secrets could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create secrets.


.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/imported_secrets/(id)/

   Update a secret. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/imported_secrets/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "item": 2
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "secret": "foobar",
        "used": false,
        "item": 2,
        "variation": null,
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the secret to modify
   :statuscode 200: no error
   :statuscode 400: The secret could not be modified due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/secret does not exist **or** you have no permission to change it.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/imported_secrets/(id)/

   Delete a secret. You can only delete secrets that have not yet been used.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/imported_secrets/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the secret to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/secret does not exist **or** you have no permission to change it **or** the secret has already been used

