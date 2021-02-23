.. _`rest-seatingplans`:

Seating plans
=============

Resource description
--------------------

The seating plan resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the plan
name                                  string                     Human-readable name of the plan
layout                                object                     JSON representation of the seating plan. These
                                                                 representations follow a JSON schema that currently
                                                                 still evolves. The version in use can be found `here`_.
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/seatingplans/

   Returns a list of all seating plans within a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/seatingplans/ HTTP/1.1
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
            "name": "Main plan",
            "layout": { … }
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/seatingplans/(id)/

   Returns information on one plan, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/seatingplans/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "Main plan",
        "layout": { … }
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the seating plan to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/seatingplans/

   Creates a new seating plan

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/seatingplans/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "Main plan",
        "layout": { … }
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 3,
        "name": "Main plan",
        "layout": { … }
      }

   :param organizer: The ``slug`` field of the organizer to create a seating plan for
   :statuscode 201: no error
   :statuscode 400: The seating plan could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/seatingplans/(id)/

   Update a plan. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field. **You can not change a plan while it is in use for
   any events.**

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/seatingplans/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "name": "Old plan"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Old plan",
        "layout": { … }
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the plan to modify
   :statuscode 200: no error
   :statuscode 400: The plan could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource **or** the plan is currently in use.

.. http:delete:: /api/v1/organizers/(organizer)/seatingplans/(id)/

   Delete a plan. You can not delete plans which are currently in use by any events.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/seatingplans/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the plan to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to delete this resource **or** the plan is currently in use.


.. _here: https://github.com/pretix/pretix/blob/master/src/pretix/static/seating/seating-plan.schema.json
