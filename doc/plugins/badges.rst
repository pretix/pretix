Badges
======

The badges plugin provides a HTTP API that exposes the various layouts used to generate PDF badges.

Resource description
--------------------

The badge layout resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal layout ID
name                                  string                     Internal layout description
default                               boolean                    ``true`` if this is the default layout
layout                                object                     Layout specification for libpretixprint
background                            URL                        Background PDF file
item_assignments                      list of objects            Products this layout is assigned to
└ item                                integer                    Item ID
===================================== ========================== =======================================================

.. versionchanged:: 1.16

   This resource has been added.


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/badgelayouts/

   Returns a list of all badge layouts

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/badgelayouts/ HTTP/1.1
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
            "id": 1,
            "name": "Default layout",
            "default": true,
            "layout": {…},
            "background": {},
            "item_assignments": []
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/badgelayouts/(id)/

   Returns information on layout.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/layoutsbadge/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "name": "Default layout",
        "default": true,
        "layout": {…},
        "background": {},
        "item_assignments": []
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the layout to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/badgeitems/

   Returns a list of all assignments of items to layouts

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/badgeitems/ HTTP/1.1
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
            "id": 1,
            "layout": 2,
            "item": 3,
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.
