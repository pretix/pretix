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
