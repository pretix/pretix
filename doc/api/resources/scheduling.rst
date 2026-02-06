Scheduling
==========

.. note:: This API is only available when the plugin **pretix-scheduling** is installed (pretix Hosted and Enterprise only).

The scheduling plugin allows you to manage resources, their types, and any plannings.

The plugin exposes a REST API, that requires the usual :ref:`rest-auth`.

Type resource
-------------

The type resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID in pretix
organizer                             integer                    Internal ID for Organizer in pretix
name                                  string                     Type name
name_plural                           string                     Plural form of the type's name
confirmation_pending_email_subject    string                     Template for pending confirmation email subject
confirmation_pending_email_template   string                     Template for pending econfirmation mail
confirmation_email_subject            string                     Template for confirmation email subject
confirmation_email_template           string                     Template for confirmation email
is_human                              boolean                    Enables lead scanning app
===================================== ========================== =======================================================

Resource resource
-----------------

The resource resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID in pretix
organizer                             integer                    Internal ID for Organizer in pretix
type                                  integer                    Internal ID for resource type in pretix
property_values                       list of strings            Order code of the order the scanned attendee belongs to
managed_by                            list of integers           ???
name                                  string                     Resource name
locale                                string                     Locale name
active                                boolean                    Deleted resources will have this set to false
notification_email                    string                     The email address to send confirmation emails to when a
                                                                 planning is created.
confirmation_required                 boolean                    Does this resource require confirmation when a planning
                                                                 is created for it.
===================================== ========================== =======================================================

Manager invite resource
-----------------------

The manager invite resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID in pretix
email                                 string                     The invitee's email address
===================================== ========================== =======================================================

Manager resource
----------------

The manager resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID in pretix
email                                 string                     The managers's email address
===================================== ========================== =======================================================

Property resource
-----------------

The property resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID in pretix
resource_type                         integer                    Internal ID in pretix for the property's resource type
name                                  string                     Property name
===================================== ========================== =======================================================

Value resource
--------------

The value resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID in pretix
prop                                  integer                    Internal ID in pretix for the value's property
value                                 string                     Value's human-readable name
===================================== ========================== =======================================================

Planning resource
-----------------

The planning resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal ID in pretix
resource                              integer                    Internal ID in pretix for the planning's organizer
requirment                            integer                    Internal ID in pretix for the planning's requirement
subevent                              integer                    Internal ID in pretix for the planning's subevent
status                                string                     Status for the planning, can be one of ``requested``,
                                                                 ``confirmed``, ``completed``, or ``cancelled``.
invoiced                              boolean                    Should this planning be invoiced?
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/resource-types/

   Returns a list of all resource types configured for an organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/resource-types/ HTTP/1.1
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
            "organizer": 1,
            "name": {
              "en": "New Name"
            },
            "name_plural": {
              "en": "Old Names",
            },
            "confirmation_pending_email_subject": {
              "en": "Pending subject",
            },
            "confirmation_pending_email_template": {
              "en": "To whom it may concern…",
            },
            "confirmation_email_subject": {
              "en": "Confirmation subject",
            },
            "confirmation_email_template": {
              "en": "To whom it may concern…",
            },
            "is_human": false,
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/resource-types/

   Create a resource type configured for an organizer.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/resource-types/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "organizer": 1,
        "name": "My Type",
        "name_plural": "My Types",
        "confirmation_pending_email_subject": "Pending subject",
        "confirmation_pending_email_template": "To whom it may concern…",
        "confirmation_email_subject": "Confirmation subject",
        "confirmation_email_template": "To whom it may concern…",
        "is_human": false,
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "organizer": 1,
        "name": {
          "en": "New Name"
        },
        "name_plural": {
          "en": "Old Names",
        },
        "confirmation_pending_email_subject": {
          "en": "Pending subject",
        },
        "confirmation_pending_email_template": {
          "en": "To whom it may concern…",
        },
        "confirmation_email_subject": {
          "en": "Confirmation subject",
        },
        "confirmation_email_template": {
          "en": "To whom it may concern…",
        },
        "is_human": false,
      }

   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/resource-types/(id)/

   Returns information on one resource type, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/resource-types/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "organizer": 1,
        "name": {
          "en": "New Name"
        },
        "name_plural": {
          "en": "Old Names",
        },
        "confirmation_pending_email_subject": {
          "en": "Pending subject",
        },
        "confirmation_pending_email_template": {
          "en": "To whom it may concern…",
        },
        "confirmation_email_subject": {
          "en": "Confirmation subject",
        },
        "confirmation_email_template": {
          "en": "To whom it may concern…",
        },
        "is_human": false,
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the resource type to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource type does not exist **or** you have no permission to view it.
   :statuscode 404: The requested resource type does not exist

.. http:patch:: /api/v1/organizers/(organizer)/resource-types/(id)/

   Update a resource type. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/resource-types/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "name": "New Name"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "organizer": 1,
        "name": {
          "en": "New Name"
        },
        "name_plural": {
          "en": "Old Names",
        },
        "confirmation_pending_email_subject": {
          "en": "Pending subject",
        },
        "confirmation_pending_email_template": {
          "en": "To whom it may concern…",
        },
        "confirmation_email_subject": {
          "en": "Confirmation subject",
        },
        "confirmation_email_template": {
          "en": "To whom it may concern…",
        },
        "is_human": false,
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param id: The ``id`` field of the resource type to update
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource type does not exist **or** you have no permission to view it.
   :statuscode 404: The requested resource type does not exist

.. http:get:: /api/v1/organizers/(organizer)/resources/

   Returns a list of all resources configured for an organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/resources/ HTTP/1.1
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
            "organizer": 4,
            "type": 5,
            "property_values": [2, 3, 4],
            "managed_by": [7, 8, 9],
            "name": "My Resource",
            "locale": "en",
            "active": true,
            "notification_email": "",
            "confirmation_required": false,
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/resources/

   Create a resource configured for an organizer.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/resources/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "organizer": 4,
        "type": 5,
        "property_values": [2, 3, 4],
        "managed_by": [7, 8, 9],
        "name": "My Resource",
        "locale": "en",
        "active": true,
        "notification_email": "",
        "confirmation_required": false,
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "organizer": 4,
        "type": 5,
        "property_values": [2, 3, 4],
        "managed_by": [7, 8, 9],
        "name": "My Resource",
        "locale": "en",
        "active": true,
        "notification_email": "",
        "confirmation_required": false,
      }

   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/resources/(id)/

   Returns information on one resource, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/resources/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "organizer": 4,
        "type": 5,
        "property_values": [2, 3, 4],
        "managed_by": [7, 8, 9],
        "name": "My Resource",
        "locale": "en",
        "active": true,
        "notification_email": "",
        "confirmation_required": false,
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the resource to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.
   :statuscode 404: The requested resource does not exist

.. http:patch:: /api/v1/organizers/(organizer)/resources/(id)/

   Update a resource. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/resources/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "name": "New Resource"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "organizer": 4,
        "type": 5,
        "property_values": [2, 3, 4],
        "managed_by": [7, 8, 9],
        "name": New Resource,
        "locale": "en",
        "active": true,
        "notification_email": "",
        "confirmation_required": false,
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param id: The ``id`` field of the resource to update
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.
   :statuscode 404: The requested resource does not exist

.. http:get:: /api/v1/organizers/(organizer)/resources/(resource)/invites/

   Returns a list of all invites for a resource.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/resources/7/invites/ HTTP/1.1
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
            "email": "mark@example.org",
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param resource: The ``id`` field of a valid resource
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/resources/(resource)/invites/

   Create an invite to manage a resource.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/resources/7/invites/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "email": "mark@example.org",
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "email": "mark@example.org",
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param resource: The ``id`` field of a valid resource
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/resources/(resource)/invites/(id)/

   Returns information on one invite, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/resources/7/invites/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "email": "mark@example.org",
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param resource: The ``id`` field of a valid resource
   :param id: The ``id`` field of the invite to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.
   :statuscode 404: The requested invite does not exist

.. http:post:: /api/v1/organizers/(organizer)/resources/(resource)/invites/(id)/resend/

   Resend the invitation email for an invite.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/resources/7/invites/1/resend/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

   :param organizer: The ``slug`` field of a valid organizer
   :param resource: The ``id`` field of a valid resource
   :param id: The ``id`` field of the invite to resend the invitation email to
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.
   :statuscode 404: The requested invite does not exist

.. http:get:: /api/v1/organizers/(organizer)/resources/(resource)/managers/

   Returns a list of all managers for a resource.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/resources/7/managers/ HTTP/1.1
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
            "email": "mark@example.org",
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param resource: The ``id`` field of a valid resource
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/resources/(resource)/managers/

   Add a user to the resource as a manager.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/resources/7/managers/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "email": "mark@example.org",
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "email": "mark@example.org",
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param resource: The ``id`` field of a valid resource
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/resources/(resource)/managers/(id)/

   Returns information on one manager, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/resources/7/managers/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "email": "mark@example.org",
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param resource: The ``id`` field of a valid resource
   :param id: The ``id`` field of the manager to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.
   :statuscode 404: The requested manager does not exist

.. http:patch:: /api/v1/organizers/(organizer)/resources/(resource)/managers/(id)/

   Update a resource. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/resources/7/managers/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 31

      {
        "email": "mark@example.org"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "email": "mark@example.org",
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param resource: The ``id`` field of a valid resource
   :param id: The ``id`` field of the manager to update
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or resource does not exist **or** you have no permission to view it.
   :statuscode 404: The requested manager does not exist

.. http:get:: /api/v1/organizers/(organizer)/properties/

   Returns a list of all properties configured for an organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/properties/ HTTP/1.1
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
            "resource_type": 4,
            "name": "My Property",
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/properties/

   Create a property configured for an organizer.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/properties/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "resource_type": 4,
        "name": "My Property",
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "resource_type": 4,
        "name": "My Property",
      }

   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/properties/(id)/

   Returns information on one property, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/properties/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "resource": 4,
        "subevent": 5,
        "requirement": 6,
        "status": "requested",
        "invoiced": false,
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the property to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or property does not exist **or** you have no permission to view it.
   :statuscode 404: The requested property does not exist

.. http:patch:: /api/v1/organizers/(organizer)/properties/(id)/

   Update a property. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/properties/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "name": "New Property"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "resource_type": 4,
        "name": "New Property",
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param id: The ``id`` field of the property to update
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or property does not exist **or** you have no permission to view it.
   :statuscode 404: The requested property does not exist

.. http:get:: /api/v1/organizers/(organizer)/properties/(property)/values/

   Returns a list of all values configured for a property and an organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/properties/1/values/ HTTP/1.1
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
            "prop": 4,
            "value": "My Value",
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param property: The ``id`` field of a valid property
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or property does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/properties/(property)/values/

   Create a value configured for a property and an organizer.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/properties/1/values/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "prop": 4,
        "value": "My Value",
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "prop": 4,
        "value": "My Value",
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param property: The ``id`` field of a valid property
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or property does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/properties/(property)/values/(id)/

   Returns information on one value, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/properties/1/values/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "prop": 4,
        "value": "My Value",
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param property: The ``id`` field of a valid property
   :param id: The ``id`` field of the value to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer, property, or value does not exist **or** you have no permission to view it.
   :statuscode 404: The requested value does not exist

.. http:patch:: /api/v1/organizers/(organizer)/properties/(property)/values/(id)/

   Update a value. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/properties/1/values/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "value": "New Value"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "prop": 4,
        "value": "New Value",
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param property: The ``id`` field of a valid property
   :param id: The ``id`` field of the value to update
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer, property, or value does not exist **or** you have no permission to view it.
   :statuscode 404: The requested value does not exist

.. http:get:: /api/v1/organizers/(organizer)/plannings/

   Returns a list of all plannings configured for an organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/plannings/ HTTP/1.1
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
            "resource": 4,
            "subevent": 5,
            "requirement": 6,
            "status": "requested",
            "invoiced": false,
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/plannings/

   Create a planning configured for an organizer.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/plannings/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

      {
        "resource": 4,
        "subevent": 5,
        "requirement": 6,
        "status": "requested",
        "invoiced": false,
      }


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "resource": 4,
        "subevent": 5,
        "requirement": 6,
        "status": "requested",
        "invoiced": false,
      }

   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 201: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/plannings/(id)/

   Returns information on one planning, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/plannings/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "resource": 4,
        "subevent": 5,
        "requirement": 6,
        "status": "requested",
        "invoiced": false,
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param id: The ``id`` field of the planning to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/planning does not exist **or** you have no permission to view it.
   :statuscode 404: The requested planning does not exist

.. http:patch:: /api/v1/organizers/(organizer)/plannings/(id)/

   Update a planning. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/plannings/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "status": "confirmed"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "resource": 4,
        "subevent": 5,
        "requirement": 6,
        "status": "confirmed",
        "invoiced": false,
      }

   :param organizer: The ``slug`` field of a valid organizer
   :param id: The ``id`` field of the planning to update
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or planning does not exist **or** you have no permission to view it.
   :statuscode 404: The requested planning does not exist

.. http:delete:: /api/v1/organizers/(organizer)/plannings/(id)/

   Cancel a planning.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/plannings/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 OK
      Vary: Accept
      Content-Type: text/javascript

   :param organizer: The ``slug`` field of a valid organizer
   :param id: The ``id`` field of the planning to cancel
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or planning does not exist **or** you have no permission to view it.
   :statuscode 404: The requested planning does not exist
