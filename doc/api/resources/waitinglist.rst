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
email                                 string                     Email address of the user on the waiting list
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
