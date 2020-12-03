Organizers
==========

Resource description
--------------------

An organizers is an entity running any number of events. In pretix, every event belongs to one
organizer and various settings, such as teams and permissions, are managed on organizer level.

The organizer resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
name                                  string                     The organizer's full name, i.e. the name of an
                                                                 organization or company.
slug                                  string                     A short form of the name, used e.g. in URLs.
===================================== ========================== =======================================================


Endpoints
---------

.. http:get:: /api/v1/organizers/

   Returns a list of all organizers the authenticated user/token has access to.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/ HTTP/1.1
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
            "name": "Big Events LLC",
            "slug": "Big Events",
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :query string ordering: Manually set the ordering of results. Valid fields to be used are ``slug`` and
                           ``name``. Default: ``slug``.
   :statuscode 200: no error
   :statuscode 401: Authentication failure

.. http:get:: /api/v1/organizers/(organizer)/

   Returns information on one organizer account, identified by its slug.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "name": "Big Events LLC",
        "slug": "Big Events",
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

Organizer settings
------------------

pretix organizers and events have lots and lots of parameters of different types that are stored in a key-value store on our system.
Since many of these settings depend on each other in complex ways, we can not give direct access to all of these
settings through the API. However, we do expose many of the simple and useful flags through the API.

Please note that the available settings flags change between pretix versions, and we do not give a guarantee on backwards-compatibility like with other parts of the API.
Therefore, we're also not including a list of the options here, but instead recommend to look at the endpoint output
to see available options. The ``explain=true`` flag enables a verbose mode that provides you with human-readable
information about the properties.

.. note:: Please note that this is not a complete representation of all organizer settings. You will find more settings
          in the web interface.

.. warning:: This API is intended for advanced users. Even though we take care to validate your input, you will be
             able to break your shops using this API by creating situations of conflicting settings. Please take care.

.. versionchanged:: 3.14

   Initial support for settings has been added to the API.

.. http:get:: /api/v1/organizers/(organizer)/settings/

   Get current values of organizer settings.

   Permission required: "Can change organizer settings"

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/settings/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example standard response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "event_list_type": "calendar",
        …
      }

   **Example verbose response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "event_list_type":
          {
            "value": "calendar",
            "label": "Default overview style",
            "help_text": "If your event series has more than 50 dates in the future, only the month or week calendar can be used."
          }
        },
        …
      }

   :param organizer: The ``slug`` field of the organizer to access
   :query explain: Set to ``true`` to enable verbose response mode
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view this resource.

.. http:patch:: /api/v1/organizers/(organizer)/settings/

   Updates organizer settings. Note that ``PUT`` is not allowed here, only ``PATCH``.

    .. warning::

       Settings can be stored at different levels in pretix. If a value is not set on organizer level, a default setting
       from a higher level (global) will be returned. If you explicitly set a setting on organizer level, it
       will no longer be inherited from the higher levels. Therefore, we recommend you to send only settings that you
       explicitly want to set on organizer level. To unset a settings, pass ``null``.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/settings/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "event_list_type": "calendar"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "event_list_type": "calendar",
        …
      }

   :param organizer: The ``slug`` field of the organizer to update
   :statuscode 200: no error
   :statuscode 400: The organizer could not be updated due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to create this resource.
