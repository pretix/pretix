Item categories
===============

Resource description
--------------------

Categories provide grouping for items (better known as products).
The category resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the category
name                                  multi-lingual string       The category's visible name
description                           multi-lingual string       A public description (might include markdown, can
                                                                 be ``null``)
position                              integer                    An integer, used for sorting the categories
is_addon                              boolean                    If ``True``, items within this category are not on sale
                                                                 on their own but the category provides a source for
                                                                 defining add-ons for other products.
===================================== ========================== =======================================================


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/categories/

   Returns a list of all categories within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/categories/ HTTP/1.1
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
            "name": {"en": "Tickets"},
            "description": {"en": "Tickets are what you need to get in."},
            "position": 1,
            "is_addon": false
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1
   :query boolean is_addon: If set to ``true`` or ``false``, only categories with this value for the field ``is_addon`` will be
                            returned.
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``id`` and ``position``.
                           Default: ``position``
   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/categories/(id)/

   Returns information on one category, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/categories/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "name": {"en": "Tickets"},
        "description": {"en": "Tickets are what you need to get in."},
        "position": 1,
        "is_addon": false
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the category to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource.
