Item Meta Properties
====================

Resource description
--------------------

An Item Meta Property is used to include (event internally relevant) meta information with every item (product). This
could be internal categories like booking positions.

The Item Meta Properties resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Unique ID for this property
name                                  string                     Name of the property
default                               string                     Value of the default option
required                              boolean                    If ``true``, this property will have to be assigned a
                                                                 value in all items of the related event
allowed_values                        list                       List of all permitted values for this property,
                                                                 or ``null`` for no limitation
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/item_meta_properties/

   Returns a list of all Item Meta Properties within a given event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/item_meta_properties/ HTTP/1.1
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
            "name": "Color",
            "default": "red",
            "required": true,
            "allowed_values": ["red", "green", "blue"]
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer
   :param event: The ``slug`` field of the event
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/item_meta_properties/(id)/

   Returns information on one property, identified by its id.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/item_meta_properties/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      {
        "id": 1,
        "name": "Color",
        "default": "red",
        "required": true,
        "allowed_values": ["red", "green", "blue"]
      }

   :param organizer: The ``slug`` field of the organizer
   :param event: The ``slug`` field of the event
   :param id: The ``id`` field of the item meta property to retrieve
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/item_meta_properties/

   Creates a new item meta property

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/item_meta_properties/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "ref-code",
        "default": "abcde",
        "required": true,
        "allowed_values": null
      }


   **Example response**:

   .. sourcecode:: http

    {
        "id": 2,
        "name": "ref-code",
        "default": "abcde",
        "required": true,
        "allowed_values": null
    }

   :param organizer: The ``slug`` field of the organizer
   :param event: The ``slug`` field of the event
   :statuscode 201: no error
   :statuscode 400: The item meta property could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/item_meta_properties/(id)/

   Update an item meta property. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide
   all fields of the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the
   fields that you want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/item_meta_properties/2/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "required": false
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "name": "ref-code",
        "default": "abcde",
        "required": false,
        "allowed_values": []
      }

   :param organizer: The ``slug`` field of the organizer
   :param event: The ``slug`` field of the event
   :param id: The ``id`` field of the item meta property to modify
   :statuscode 200: no error
   :statuscode 400: The property could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/item_meta_properties/(id)/

   Delete an item meta property.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/item_meta_properties/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer
   :param event: The ``slug`` field of the event
   :param id: The ``id`` field of the item meta property to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to delete this resource.
