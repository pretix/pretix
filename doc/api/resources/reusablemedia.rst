.. _`rest-reusablemedia`:

Reusable media
==============

Reusable media represent things, typically physical tokens like plastic cards or NFC wristbands, which can represent
other entities inside the system. For example, a medium can link to an order position or to a gift card and can be used
in their place. Later, the medium might be reused for a different ticket.

Resource description
--------------------

The reusable medium resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID of the medium
type                                  string                     Type of medium, e.g. ``"barcode"``, ``"nfc_uid"`` or ``"nfc_mf0aes"``.
organizer                             string                     Organizer slug of the organizer who "owns" this medium.
identifier                            string                     Unique identifier of the medium. The format depends on the ``type``.
active                                boolean                    Whether this medium may be used.
created                               datetime                   Date of creation
updated                               datetime                   Date of last modification
expires                               datetime                   Expiry date (or ``null``)
customer                              string                     Identifier of a customer account this medium belongs to.
linked_orderposition                  integer                    Internal ID of a ticket this medium is linked to.
linked_giftcard                       integer                    Internal ID of a gift card this medium is linked to.
info                                  object                     Additional data, content depends on the ``type``. Consider
                                                                 this internal to the system and don't use it for your own data.
notes                                 string                     Internal notes and comments (or ``null``)
===================================== ========================== =======================================================

Existing media types are:

- ``barcode``
- ``nfc_uid``
- ``nfc_mf0aes``

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/reusablemedia/

   Returns a list of all media issued by a given organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/reusablemedia/ HTTP/1.1
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
            "organizer": "bigevents",
            "identifier": "ABCDEFGH",
            "created": "2021-04-06T13:44:22.809377Z",
            "updated": "2021-04-06T13:44:22.809377Z",
            "type": "barcode",
            "active": True,
            "expires": None,
            "customer": None,
            "linked_orderposition": None,
            "linked_giftcard": None,
            "notes": None,
            "info": {}
          }
        ]
      }

   :query integer page: The page number in case of a multi-page result set, default is 1.
   :query string identifier: Only show media with the given identifier. Note that you should use the lookup endpoint described below for most use cases.
   :query string type: Only show media with the given type.
   :query boolean active: Only show media that are (not) active.
   :query string customer: Only show media linked to the given customer.
   :query string created_since: Only show media created since a given date.
   :query string updated_since: Only show media updated since a given date.
   :query integer linked_orderposition: Only show media linked to the given ticket.
   :query integer linked_giftcard: Only show media linked to the given gift card.
   :query string expand: If you pass ``"linked_giftcard"``, ``"linked_giftcard.owner_ticket"``, ``"linked_orderposition"``,
                         or ``"customer"``, the respective field will be shown as a nested value instead of just an ID.
                         The nested objects are identical to the respective resources, except that order positions
                         will have an attribute of the format ``"order": {"code": "ABCDE", "event": "eventslug"}`` to make
                         matching easier. The parameter can be given multiple times.
   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/reusablemedia/(id)/

   Returns information on one medium, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/reusablemedia/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "organizer": "bigevents",
        "identifier": "ABCDEFGH",
        "created": "2021-04-06T13:44:22.809377Z",
        "updated": "2021-04-06T13:44:22.809377Z",
        "type": "barcode",
        "active": True,
        "expires": None,
        "customer": None,
        "linked_orderposition": None,
        "linked_giftcard": None,
        "notes": None,
        "info": {}
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the medium to fetch
   :query string expand: If you pass ``"linked_giftcard"``, ``"linked_giftcard.owner_ticket"``, ``"linked_orderposition"``,
                         or ``"customer"``, the respective field will be shown as a nested value instead of just an ID.
                         The nested objects are identical to the respective resources, except that order positions
                         will have an attribute of the format ``"order": {"code": "ABCDE", "event": "eventslug"}`` to make
                         matching easier. The parameter can be given multiple times.
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/reusablemedia/lookup/

   Look up a new reusable medium by its identifier. In some cases, this might lead to the automatic creation of a new
   medium behind the scenes.

   This endpoint, and this endpoint only, might return media from a different organizer if there is a cross-acceptance
   agreement. In this case, only linked gift cards will be returned, no order position or customer records,

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/reusablemedia/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "identifier": "ABCDEFGH",
        "type": "barcode",
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "organizer": "bigevents",
        "identifier": "ABCDEFGH",
        "created": "2021-04-06T13:44:22.809377Z",
        "updated": "2021-04-06T13:44:22.809377Z",
        "type": "barcode",
        "active": True,
        "expires": None,
        "customer": None,
        "linked_orderposition": None,
        "linked_giftcard": None,
        "notes": None,
        "info": {}
      }

   :param organizer: The ``slug`` field of the organizer to look up a medium for
   :query string expand: If you pass ``"linked_giftcard"``, ``"linked_orderposition"``, oder ``"customer"``, the respective
                         field will be shown as a nested value instead of just an ID. The nested objects are identical to
                         the respective resources, except that the ``linked_orderposition`` will have an attribute of the
                         format ``"order": {"code": "ABCDE", "event": "eventslug"}`` to make matching easier. The parameter
                         can be given multiple times.
   :statuscode 201: no error
   :statuscode 400: The medium could not be looked up due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:post:: /api/v1/organizers/(organizer)/reusablemedia/

   Creates a new reusable medium.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/reusablemedia/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "identifier": "ABCDEFGH",
        "type": "barcode",
        "active": True,
        "expires": None,
        "customer": None,
        "linked_orderposition": None,
        "linked_giftcard": None,
        "notes": None,
        "info": {}
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "organizer": "bigevents",
        "identifier": "ABCDEFGH",
        "created": "2021-04-06T13:44:22.809377Z",
        "updated": "2021-04-06T13:44:22.809377Z",
        "type": "barcode",
        "active": True,
        "expires": None,
        "customer": None,
        "linked_orderposition": None,
        "linked_giftcard": None,
        "notes": None,
        "info": {}
      }

   :param organizer: The ``slug`` field of the organizer to create a medium for
   :query string expand: If you pass ``"linked_giftcard"``, ``"linked_orderposition"``, oder ``"customer"``, the respective
                         field will be shown as a nested value instead of just an ID. The nested objects are identical to
                         the respective resources, except that the ``linked_orderposition`` will have an attribute of the
                         format ``"order": {"code": "ABCDE", "event": "eventslug"}`` to make matching easier. The parameter
                         can be given multiple times.
   :statuscode 201: no error
   :statuscode 400: The medium could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/reusablemedia/(id)/

   Update a reusable medium. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   You can change all fields of the resource except the ``id``, ``identifier`` and ``type`` fields.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/reusablemedia/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 94

      {
        "linked_orderposition": 13
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "organizer": "bigevents",
        "identifier": "ABCDEFGH",
        "created": "2021-04-06T13:44:22.809377Z",
        "updated": "2021-04-06T13:44:22.809377Z",
        "type": "barcode",
        "active": True,
        "expires": None,
        "customer": None,
        "linked_orderposition": 13,
        "linked_giftcard": None,
        "notes": None,
        "info": {}
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param id: The ``id`` field of the medium to modify
   :query string expand: If you pass ``"linked_giftcard"``, ``"linked_orderposition"``, oder ``"customer"``, the respective
                         field will be shown as a nested value instead of just an ID. The nested objects are identical to
                         the respective resources, except that the ``linked_orderposition`` will have an attribute of the
                         format ``"order": {"code": "ABCDE", "event": "eventslug"}`` to make matching easier. The parameter
                         can be given multiple times.
   :statuscode 200: no error
   :statuscode 400: The medium could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.
