Event Meta Properties
=====================

Resource description
--------------------

An event meta property is used to to define meta information fields for its events.
This information can be re-used, for example, in ticket layouts.

The event meta property resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Unique ID for this property
name                                  string                     Name of the property
default                               string                     Value of the default option
required                              boolean                    If ``true``, an event can only be taken live if the
                                                                 property is set. In event series, it's always optional
                                                                 to set a value for individual dates
protected                             boolean                    If ``true``, the value for an event can only be changed
                                                                 by organizer-level administrators
filter_public                         boolean                    If ``true``, this property will be shown to filter
                                                                 events in the public event list and calendar
public_label                          string                     Public name of the property
filter_allowed                        boolean                    If ``true``, this property will be shown to filter
                                                                 events or reports in the backend, and it can also be
                                                                 used for hidden filter parameters in the frontend
choices                               list of objects            List of JSON objects representing all permitted values
                                                                 for this property, or ``null`` for no limitation.
                                                                 Each choice object has a required internal name named
                                                                 ``key`` and optional public name named ``label``
                                                                 consisting of a dictionary of i18n string translations,
                                                                 as well as other implementation based key-value-pairs
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/event_meta_properties/

   Returns a list of all meta properties for the organizer.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/meta_properties/ HTTP/1.1
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
            "default": "blue",
            "required": false,
            "protected": false,
            "filter_public": false,
            "public_label": {},
            "filter_allowed": true,
            "choices": [
                {
                    "key": "blue",
                    "ORDER": 1,
                    "label": {
                        "en": "Blue"
                    },
                    "DELETE": false
                }
            ]
          }
        ]
      }

   :param organizer: The ``slug`` field of the organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:get:: /api/v1/organizers/(organizer)/event_meta_properties/(id)/

   Returns information on one property, identified by its id.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/event_meta_properties/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      {
        "id": 1,
        "name": "Color",
        "default": "blue",
        "required": false,
        "protected": false,
        "filter_public": false,
        "public_label": {},
        "filter_allowed": true,
        "choices": null
      }

   :param organizer: The ``slug`` field of the organizer
   :param id: The ``id`` field of the meta property to retrieve
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:post:: /api/v1/organizers/(organizer)/event_meta_properties/

   Creates a new meta property

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/event_meta_properties/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "name": "ref-code",
        "default": "abcde",
        "required": true,
        "choices": null
      }


   **Example response**:

   .. sourcecode:: http

    {
        "id": 2,
        "name": "reference",
        "default": "abcde",
        "required": true,
        "protected": false,
        "filter_public": false,
        "public_label": null,
        "filter_allowed": true,
        "choices": null
    }

   :param organizer: The ``slug`` field of the organizer
   :statuscode 201: no error
   :statuscode 400: The meta property could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.

.. http:patch:: /api/v1/organizers/(organizer)/event_meta_properties/(id)/

   Update a meta property. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide
   all fields of the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the
   fields that you want to change.

   You can change all fields of the resource except the ``id`` field.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/event_meta_properties/2/ HTTP/1.1
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
        "id": 3,
        "name": "reference",
        "default": "abcde",
        "required": false,
        "protected": false,
        "filter_public": false,
        "public_label": null,
        "filter_allowed": true,
        "choices": null
      }

   :param organizer: The ``slug`` field of the organizer
   :param id: The ``id`` field of the meta property to modify
   :statuscode 200: no error
   :statuscode 400: The property could not be modified due to invalid submitted data
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to change this resource.

.. http:delete:: /api/v1/organizers/(organizer)/event_meta_properties/(id)/

   Delete a meta property.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/event_meta_properties/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer
   :param id: The ``id`` field of the meta property to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to delete this resource.
