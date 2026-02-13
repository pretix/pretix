Item program times
==================

Resource description
--------------------

Program times for products (items) that can be set in addition to event times, e.g. to display seperate schedules within an event.
Note that ``program_times`` are not available for items inside event series.
The program times resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the program time
start                                 datetime                   The start date time for this program time slot.
end                                   datetime                   The end date time for this program time slot.
===================================== ========================== =======================================================

.. versionchanged:: TODO

   The resource has been added.


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/program_times/

   Returns a list of all program times for a given item.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/11/program_times/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
         "count": 3,
         "next": null,
         "previous": null,
         "results": [
            {
               "id": 2,
               "start": "2025-08-14T22:00:00Z",
               "end": "2025-08-15T00:00:00Z"
            },
            {
               "id": 3,
               "start": "2025-08-12T22:00:00Z",
               "end": "2025-08-13T22:00:00Z"
            },
            {
               "id": 14,
               "start": "2025-08-15T22:00:00Z",
               "end": "2025-08-17T22:00:00Z"
            }
        ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param item: The ``id`` field of the item to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/item does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/program_times/(id)/

   Returns information on one program time, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/items/1/program_times/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
         "id": 1,
         "start": "2025-08-15T22:00:00Z",
         "end": "2025-10-27T23:00:00Z"
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param item: The ``id`` field of the item to fetch
   :param id: The ``id`` field of the program time to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/program_times/

   Creates a new program time

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/items/1/program_times/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "start": "2025-08-15T10:00:00Z",
        "end": "2025-08-15T22:00:00Z"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 17,
        "start": "2025-08-15T10:00:00Z",
        "end": "2025-08-15T22:00:00Z"
      }

   :param organizer: The ``slug`` field of the organizer of the event/item to create a program time for
   :param event: The ``slug`` field of the event to create a program time for
   :param item: The ``id`` field of the item to create a program time for
   :statuscode 201: no error
   :statuscode 400: The program time could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/items/(item)/program_times/(id)/

   Update a program time. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/items/1/program_times/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "start": "2025-08-14T10:00:00Z"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "start": "2025-08-14T10:00:00Z",
        "end": "2025-08-15T12:00:00Z"
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to modify
   :param id: The ``id`` field of the program time to modify
   :statuscode 200: no error
   :statuscode 400: The program time could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/items/(id)/program_times/(id)/

   Delete a program time.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/items/1/program_times/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the item to modify
   :param id: The ``id`` field of the program time to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.
