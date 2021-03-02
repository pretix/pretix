Waiting list entries
====================

Resource description
--------------------

The waiting list entry resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the waiting list entry
created                               datetime                   Creation date of the waiting list entry
name                                  string                     Name of the user on the waiting list
email                                 string                     Email address of the user on the waiting list
phone                                 string                     Phone number of the user on the waiting list
voucher                               integer                    Internal ID of the voucher sent to this user. If
                                                                 this field is set, the user has been sent a voucher
                                                                 and is no longer waiting. If it is ``null``, the
                                                                 user is still waiting.
item                                  integer                    An ID of an item the user is waiting to be available
                                                                 again
variation                             integer                    An ID of a variation the user is waiting to be
                                                                 available again (or ``null``)
locale                                string                     Locale of the waiting user
subevent                              integer                    ID of the date inside an event series this entry belongs to (or ``null``).
===================================== ========================== =======================================================


.. versionchanged:: 1.15

   The write operations ``POST``, ``PATCH``, ``PUT``, and ``DELETE`` have been added as well as a method to send out
   vouchers.


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/waitinglistentries/

   Returns a list of all waiting list entries within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/waitinglistentries/ HTTP/1.1
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
            "created": "2017-12-01T10:00:00Z",
            "email": "waiting@example.org",
            "voucher": null,
            "item": 2,
            "variation": null,
            "locale": "en",
            "subevent": null
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query string email: Only show waiting list entries created with the given email address.
   :query string locale: Only show waiting list entries created with the given locale.
   :query boolean has_voucher: If set to ``true`` or ``false``, only waiting list entries are returned that have or
                               have not been sent a voucher.
   :query integer item: If set, only entries of users waiting for the item with the given ID will be shown.
   :query integer variation: If set, only entries of users waiting for the variation with the given ID will be shown.
   :query integer subevent: Only return entries of the sub-event with the given ID
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id``, ``created``,
                           ``email``, ``item``. Default: ``created``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/waitinglistentries/(id)/

   Returns information on one waiting list entry, identified by its internal ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/waitinglistentries/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "created": "2017-12-01T10:00:00Z",
        "email": "waiting@example.org",
        "voucher": null,
        "item": 2,
        "variation": null,
        "locale": "en",
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the waiting list entry to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/waitinglistentries/

   Create a new entry.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/waitinglistentries/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 408

      {
        "email": "waiting@example.org",
        "item": 3,
        "variation": null,
        "locale": "de",
        "subevent": null
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "created": "2017-12-01T10:00:00Z",
        "email": "waiting@example.org",
        "voucher": null,
        "item": 3,
        "variation": null,
        "locale": "de",
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to create an entry for
   :param event: The ``slug`` field of the event to create an entry for
   :statuscode 201: no error
   :statuscode 400: The voucher could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this
                    resource **or** entries cannot be created for this item at this time.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/waitinglistentries/(id)/

   Update an entry. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id``, ``voucher`` and ``created`` fields. You can only change
   an entry as long as no ``voucher`` is set.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/waitinglistentries/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 408

      {
        "item": 4
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "created": "2017-12-01T10:00:00Z",
        "email": "waiting@example.org",
        "voucher": null,
        "item": 4,
        "variation": null,
        "locale": "de",
        "subevent": null
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the entry to modify
   :statuscode 200: no error
   :statuscode 400: The entry could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this
                    resource **or** entries cannot be created for this item at this time **or** this entry already
                    has a voucher assigned

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/waitinglistentries/(id)/send_voucher/

   Manually sends a voucher to someone on the waiting list

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/waitinglistentries/1/send_voucher/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 0

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the entry to modify
   :statuscode 204: no error
   :statuscode 400: The voucher could not be sent out, see body for details (e.g. voucher has already been sent or
                    item is not available).
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to do this

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/waitinglistentries/(id)/

   Delete an entry. Note that you cannot delete an entry once it is assigned a voucher.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/waitinglistentries/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the entry to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this
                    resource **or** this entry already has a voucher assigned.
