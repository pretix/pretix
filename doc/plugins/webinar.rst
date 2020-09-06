pretix Webinar
==============

Fetch host URLs
---------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/webinars/

   Returns a list of all currently available webinar calls configured for an event.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/webinars/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/json

      [
        {
          "name": "Webinar B – Sept. 8th, 2020",
          "hosturl": "http://pretix.eu/demo/museum/webinar/host/a9aded3d7bd4df60/30611a34f9fee5d3/"
        },
        {
          "name": "Webinar A – Sept. 8, 2020",
          "hosturl": "http://pretix.eu/demo/museum/webinar/host/e714x7d4a4a36a04/b9cc444665xxx757/"
        }
      ]

   :query subevent: Limit the result to the webinar(s) for a specific subevent.
   :param organizer: The ``slug`` field of a valid organizer
   :param event: The ``slug`` field of the event to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer or event does not exist **or** you have no permission to view it.
