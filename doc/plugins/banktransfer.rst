Bank transfer HTTP API
======================

The banktransfer plugin provides a HTTP API that `pretix-banktool`_ uses to send bank
transactions to the pretix server. This API is integrated with the regular :ref:`rest-api`
and therefore follows the conventions listed there.

Bank import job resource
^^^^^^^^^^^^^^^^^^^^^^^^

Resource description
--------------------

The bank import job resource contains the following public fields:

.. rst-class:: rest-resource-table

===================================== ========================== =======================================================
Field                                 Type                       Description
===================================== ========================== =======================================================
id                                    integer                    Internal job ID
event                                 string                     Slug of the event this job was uploaded for or ``null``
created                               datetime                   Job creation time
state                                 string                     Job state, one of ``pending``, ``running``,
                                                                 ``error`` or ``completed``
transactions                          list of objects            Transactions included in this job (will only appear
                                                                 after the job has started processing).
├ state                               string                     Transaction state, one of ``imported``, ``nomatch``,
                                                                 ``invalid``, ``error``, ``valid``, ``discarded``,
                                                                 ``already`` (already paid)
├ message                             string                     Error message (if any)
├ checksum                            string                     Checksum computed from payer, reference, amount and
                                                                 date
├ payer                               string                     Payment source
├ reference                           string                     Payment reference
├ amount                              string                     Payment amount
├ iban                                string                     Payment IBAN
├ bic                                 string                     Payment BIC
├ date                                string                     Payment date (in **user-inputted** format)
├ order                               string                     Associated order code (or ``null``)
└ comment                             string                     Internal comment
===================================== ========================== =======================================================

Note that the ``payer`` and ``reference`` fields are set to empty as soon as the payment is matched to an order or
discarded to avoid storing sensitive data when not necessary. The ``checksum`` persists to implement deduplication.


Endpoints
---------

.. http:get:: /api/v1/organizers/(organizer)/bankimportjobs/

   Returns a list of all bank import jobs within a given organizer the authenticated user/token has access to.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/bankimportjobs/ HTTP/1.1
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
            "state": "completed",
            "created": "2017-06-27T08:00:29Z",
            "event": "sampleconf",
            "transactions": [
              {
                "amount": "57.00",
                "comment": "",
                "date": "26.06.2017",
                "payer": "John Doe",
                "order": null,
                "iban": "",
                "bic": "",
                "checksum": "5de03a601644dfa63420dacfd285565f8375a8f2",
                "reference": "GUTSCHRIFT\r\nSAMPLECONF-NAB12 EREF: SAMPLECONF-NAB12\r\nIBAN: DE1234556…",
                "state": "nomatch",
                "message": ""
              }
             ]
          }
        ]
      }

   :query page: The page number in case of a multi-page result set, default is 1
   :query event: Return only jobs for the event with the given slug
   :query state: Return only jobs with the given state
   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to view it.

.. http:get:: /api/v1/organizers/(organizer)/bankimportjobs/(id)/

   Returns information on one job, identified by its ID.

   **Example request**:

   .. sourcecode:: http

      GET /api/v1/organizers/bigevents/bankimportjobs/1/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "state": "completed",
        "created": "2017-06-27T08:00:29Z",
        "event": "sampleconf",
        "transactions": [
          {
            "amount": "57.00",
            "comment": "",
            "date": "26.06.2017",
            "payer": "John Doe",
            "iban": "",
            "bic": "",
            "order": null,
            "checksum": "5de03a601644dfa63420dacfd285565f8375a8f2",
            "reference": "GUTSCHRIFT\r\nSAMPLECONF-NAB12 EREF: SAMPLECONF-NAB12\r\nIBAN: DE1234556…",
            "state": "nomatch",
            "message": ""
          }
         ]
      }

   :param organizer: The ``slug`` field of the organizer to fetch
   :statuscode 200: no error
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer/event does not exist **or** you have no permission to view it.

.. http:post:: /api/v1/organizers/(organizer)/bankimportjobs/

   Upload a new job and execute it.

   **Example request**:

   .. sourcecode:: http

      POST /api/v1/organizers/bigevents/bankimportjobs/ HTTP/1.1
      Host: pretix.eu
      Accept: application/json, text/javascript
      Content-Type: application/json

      {
        "event": "sampleconf",
        "transactions": [
          {
            "payer": "Foo",
            "reference": "SAMPLECONF-173AS",
            "amount": "23.00",
            "date": "2017-06-26"
          }
        ]
      }

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 201 Created
      Vary: Accept
      Content-Type: text/javascript

      {
        "id": 1,
        "state": "pending",
        "created": "2017-06-27T08:00:29Z",
        "event": "sampleconf",
        "transactions": []
      }

   .. note:: Depending on the server configuration, the job might be executed immediately, leading to a longer API
             response time but a response with state ``completed`` or ``error``, or the job might be put into a
             background queue, leading to an immediate response of state ``pending`` with an empty list of
             transactions.

   :param organizer: The ``slug`` field of a valid organizer
   :statuscode 201: no error
   :statuscode 400: Invalid input
   :statuscode 401: Authentication failure
   :statuscode 403: The requested organizer does not exist **or** you have no permission to perform this action.

.. _pretix-banktool: https://github.com/pretix/pretix-banktool
