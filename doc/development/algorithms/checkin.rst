.. spelling: libpretixsync

Check-in algorithms
===================

When a ticket is scanned at the entrance or exit of an event, we follow a series of steps to determine whether
the check-in is allowed or not. To understand some of the terms in the following diagrams, you should also check
out the documentation of the :ref:`ticket redemption API endpoint <rest-checkin-redeem>`.

Server-side
-----------

The following diagram shows the series of checks executed on the server when a ticket is redeemed through the API.
Some simplifications have been made, for example the deduplication mechanism based on the ``nonce`` parameter
to prevent re-uploads of the same scan is not shown.

.. image:: /images/checkin_online.png

Client-side
-----------

The process of verifying tickets offline is a little different. There are two different approaches,
depending on whether we have information about all tickets in the local database. The following diagram shows
the algorithm as currently implemented in recent versions of `libpretixsync`_.

.. image:: /images/checkin_offline.png

.. _libpretixsync: https://github.com/pretix/libpretixsync
