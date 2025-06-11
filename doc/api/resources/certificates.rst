Certificates of attendance
==========================

.. note:: This API is only available when the plugin **pretix-certificates** is installed (pretix Hosted and Enterprise only).

The certificates plugin provides a HTTP API that allows you to download the certificate for a specific attendee.


Certificate download
--------------------

.. http:get:: /api/v1/organizers/(organizer)/events/(event)/orderpositions/(id)/certificate/

   Downloads the certificate for one order position, identified by its internal ID. Download is a two-step
   process. You will always get a :http:statuscode:`303` response with a ``Location`` header to a different
   URL. In the background, our server starts preparing the PDF file.

   If you then do a ``GET`` to the URL you were given, you will either receive a :http:statuscode:`409` response
   indicating to retry after a few seconds, or a :http:statuscode:`200` response with the PDF file.


   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/certificate/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 303 See Other
      Location: /api/v1/organizers/democon/events/3vjrh/orderpositions/426/certificate/?result=1f550651-ae7b-4911-a76c-2be8f348aaa5

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/events/sampleconf/orderpositions/23442/certificate/?result=1f550651-ae7b-4911-a76c-2be8f348aaa5 HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: application/pdf

      ...

   :param organizer: The ``slug`` field of the organizer to fetch
   :param event: The ``slug`` field of the event to fetch
   :param id: The ``id`` field of the order position to fetch
   :statuscode 200: File ready for download
   :statuscode 303: Processing started
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view this resource
                    **or** downloads are not available for this order position at this time. The response content will
                    contain more details.
   :statuscode 404: The requested order position or download provider does not exist.
   :statuscode 409: The file is not yet ready and will now be prepared. Retry the request after waiting for a few
                    seconds.
