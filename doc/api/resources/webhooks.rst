.. _`rest-webhooks`:

Webhooks
========

.. note:: This page is about how to modify webhook settings themselves through the REST API. If you just want to know
          how webhooks work, go here: :ref:`webhooks`

Resource description
--------------------

The webhook resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the webhook
enabled                               boolean                    If ``False``, this webhook will not receive any notifications
target_url                            string                     The URL to call
all_events                            boolean                    If ``True``, this webhook will receive notifications
                                                                 on all events of this organizer
limit_events                          list of strings            If ``all_events`` is ``False``, this is a list of
                                                                 event slugs this webhook is active for
action_types                          list of strings            A list of action type filters that limit the
                                                                 notifications sent to this webhook. See below for
                                                                 valid values
===================================== ========================== =======================================================

The following values for ``action_types`` are valid with pretix core:

    * ``pretix.event.order.placed``
    * ``pretix.event.order.paid``
    * ``pretix.event.order.canceled``
    * ``pretix.event.order.expired``
    * ``pretix.event.order.modified``
    * ``pretix.event.order.contact.changed``
    * ``pretix.event.order.changed.*``
    * ``pretix.event.order.refund.created.externally``
    * ``pretix.event.order.refunded``
    * ``pretix.event.order.approved``
    * ``pretix.event.order.denied``
    * ``pretix.event.checkin``
    * ``pretix.event.checkin.reverted``

Installed plugins might register more valid values.


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/webhooks/

   Returns a list of all webhooks within a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/webhooks/ HTTP/1.1
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
            "id": 2,
            "enabled": true,
            "target_url": "https://httpstat.us/200",
            "all_events": false,
            "limit_events": ["democon"],
            "action_types": ["pretix.event.order.modified", "pretix.event.order.changed.*"]
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/webhooks/(id)/

   Returns information on one webhook, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/webhooks/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "enabled": true,
        "target_url": "https://httpstat.us/200",
        "all_events": false,
        "limit_events": ["democon"],
        "action_types": ["pretix.event.order.modified", "pretix.event.order.changed.*"]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the webhook to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/webhooks/

   Creates a new webhook

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/webhooks/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content: application/json

      {
        "enabled": true,
        "target_url": "https://httpstat.us/200",
        "all_events": false,
        "limit_events": ["democon"],
        "action_types": ["pretix.event.order.modified", "pretix.event.order.changed.*"]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "enabled": true,
        "target_url": "https://httpstat.us/200",
        "all_events": false,
        "limit_events": ["democon"],
        "action_types": ["pretix.event.order.modified", "pretix.event.order.changed.*"]
      }

   :param organizer: The ``slug`` field of the organizer to create a webhook for
   :statuscode 201: no error
   :statuscode 400: The webhook could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/webhooks/(id)/

   Update a webhook. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/webhooks/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "enabled": false
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "enabled": false,
        "target_url": "https://httpstat.us/200",
        "all_events": false,
        "limit_events": ["democon"],
        "action_types": ["pretix.event.order.modified", "pretix.event.order.changed.*"]
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the webhook to modify
   :statuscode 200: no error
   :statuscode 400: The webhook could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/webhook/(id)/

   Delete a webhook. Currently, this will not delete but just disable the webhook.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/webhooks/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the webhook to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to delete this resource.
