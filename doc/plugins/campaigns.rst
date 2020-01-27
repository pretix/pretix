Campaigns
=========

The campaigns plugin provides a HTTP API that allows you to create new campaigns.

Resource description
--------------------

The campaign resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal campaign ID
code                                  string                     The URL component of the campaign, e.g. with code ``BAR``
                                                                 the campaign URL would to be ``https://<server>/<organizer>/<event>/c/BAR/``.
                                                                 This value needs to be *globally unique* and we do not
                                                                 recommend setting it manually. If you omit it, a random
                                                                 value will be chosen.
description                           string                     An internal, human-readable name of the campaign.
external_target                       string                     An URL to redirect to from the tracking link. To redirect to
                                                                 the ticket shop, use an empty string.
order_count                           integer                    Number of orders tracked on this campaign (read-only)
click_count                           integer                    Number of clicks tracked on this campaign (read-only)
===================================== ========================== =======================================================

Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/campaigns/

   Returns a list of all campaigns configured for an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/campaigns/ HTTP/1.1
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
            "code": "wZnL11fjq",
            "description": "Facebook",
            "external_target": "",
            "order_count:" 0,
            "click_count:" 0
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/campaigns/(id)/

   Returns information on one campaign, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/campaigns/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      {
        "id": 1,
        "code": "wZnL11fjq",
        "description": "Facebook",
        "external_target": "",
        "order_count:" 0,
        "click_count:" 0
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the campaign to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/campaign does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/events/(event)/campaigns/

   Create a new campaign.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/events/sampleconf/campaigns/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 166

      {
        "description": "Twitter"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: application/json

      {
        "id": 2,
        "code": "IfVJQzSBL",
        "description": "Twitter",
        "external_target": "",
        "order_count:" 0,
        "click_count:" 0
      }

   :param organizer: The ``slug`` field of the organizer to create a campaign for
   :param event: The ``slug`` field of the event to create a campaign for
   :statuscode 201: no error
   :statuscode 400: The campaign could not be created due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to create campaigns.


.. http:patch:: /api/v1/organizers/(organizer)/events/(event)/campaigns/(id)/

   Update a campaign. You can also use ``PUT`` instead of ``PATCH``. With ``PUT``, you have to provide all fields of
   the resource, other fields will be reset to default. With ``PATCH``, you only need to provide the fields that you
   want to change.

   **Example request**:

   .. sourcecode:: http

      PATCH /api/v1/organizers/bigevents/events/sampleconf/campaigns/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json
      Content-Length: 34

      {
        "external_target": "https://mywebsite.com"
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 2,
        "code": "IfVJQzSBL",
        "description": "Twitter",
        "external_target": "https://mywebsite.com",
        "order_count:" 0,
        "click_count:" 0
      }

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the campaign to modify
   :statuscode 200: no error
   :statuscode 400: The campaign could not be modified due to invalid submitted data.
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/campaign does not exist **or** you have no permission to change it.


.. http:delete:: /api/v1/organizers/(organizer)/events/(event)/campaigns/(id)/

   Delete a campaign and all associated data.

   **Example request**:

   .. sourcecode:: http

      DELETE /api/v1/organizers/bigevents/events/sampleconf/campaigns/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 204 No Content
      Vary: Accept

   :param organizer: The ``slug`` field of the organizer to modify
   :param event: The ``slug`` field of the event to modify
   :param id: The ``id`` field of the campaign to delete
   :statuscode 204: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event/campaign does not exist **or** you have no permission to change it
