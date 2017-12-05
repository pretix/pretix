Organizer account
=================

The basis of all your operations within pretix is your organizer account. It represents an entity that is running
events, for example a company, yourself or any other institution.
Every event belongs to one organizer account and events within the same organizer account are assumed to belong together
in some sense, whereas events in different organizer accounts are completely isolated.

If you want to use the hosted pretix service, you can create an organizer account on our `Get started`_ page. Otherwise,
ask your pretix administrator for access to an organizer account.

You can find out all organizer accounts you have access to by going to your global dashboard (click on the pretix logo
in the top-left corner) and then select "Organizers" from the navigation bar on the left side. Then, choose one of the
organizer accounts presented, if there are multiple of them:

.. thumbnail:: ../../screens/organizer/list.png
   :align: center
   :class: screenshot

This overview shows you all event that belong to the organizer and you have access to:

.. thumbnail:: ../../screens/organizer/event_list.png
   :align: center
   :class: screenshot

With the "Edit" button at the top, next to the organizer account name, you can modify properties of the organizer
account such as its name and display settings for the public profile page of the organizer account:

.. thumbnail:: ../../screens/organizer/edit.png
   :align: center
   :class: screenshot

.. tip::

   The profile page will be shown as ``https://pretix.eu/slug/`` where ``slug`` is to be replaced by the short form of
   the organizer name that you entered during account creation and ``pretix.eu`` is to be replaced by your
   installation's domain name if you are not using our hosted service.

   Instead, you can also use a custom domain for the profile page and your events, for example
   ``https://tickets.example.com/`` if ``example.com`` is a domain that you own.  Head to :ref:`custom_domain` to learn
   more.

.. _Get started: https://pretix.eu/about/en/setup
