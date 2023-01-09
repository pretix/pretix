PDF ticket output
=================

The PDF ticket output plugin provides a HTTP API that exposes the various layouts used
to generate PDF tickets.

Resource description
--------------------

The ticket layout resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal layout ID
name                                  string                     Internal layout description
default                               boolean                    ``true`` if this is the default layout
layout                                list                       Dynamic layout specification. Each list element
                                                                 corresponds to one dynamic element of the layout.
                                                                 The current version of the schema in use can be found
                                                                 `here`_.
                                                                 Submitting invalid content can lead to application errors.
background                            URL                        Background PDF file
item_assignments                      list of objects            Products this layout is assigned to (currently read-only)
├ sales_channel                       string                     Sales channel (defaults to ``web``).
└ item                                integer                    Item ID
===================================== ========================== =======================================================


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/ticketlayouts/

   Returns a list of all ticket layouts

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/ticketlayouts/ HTTP/1.1
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
            "background": null,
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

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/ticketlayouts/(id)/

   Returns information on layout.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/ticketlayouts/1/ HTTP/1.1
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
        "background": null,
        "item_assignments": []
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the layout to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/ticketlayoutitems/

   Returns a list of all assignments of items to layouts

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/democon/ticketlayoutitems/ HTTP/1.1
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
            "sales_channel": web
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of a valid event
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/ticketlayouts/

   Creates a new ticket layout

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/ticketlayouts/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "Default layout",
        "default": true,
        "layout": […],
        "background": null,
        "item_assignments": []
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Default layout",
        "default": true,
        "layout": […],
        "background": null,
        "item_assignments": []
      }

   :param organizer: The ``slug`` field of the organizer of the event to create a layout for
   :param event: The ``slug`` field of the event to create a layout for
   :statuscode 201: no error
   :statuscode 400: The layout could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/ticketlayouts/(id)/

   Update a layout. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/ticketlayouts/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "name": "Default layout"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": "Default layout",
        "default": true,
        "layout": […],
        "background": null,
        "item_assignments": []
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the layout to modify
   :statuscode 200: no error
   :statuscode 400: The layout could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/ticketlayouts/(id)/

   Delete a layout.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/ticketlayouts/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the layout to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to delete this resource.


.. _here: https://github.com/pretix/pretix/blob/master/src/pretix/static/schema/pdf-layout.schema.json
