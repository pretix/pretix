Implementation Concepts
=======================

Basic terminology
-----------------

Tixl is a sofware selling **Items**, an abstract thing which is related to an **Event**. Every Event is managed by the **Organizer**, who runs the event.

Tixl know two types of **Users**:

**Local users**
    Local users do only exist inside the scope of one event. They are identified by usernames, which are only valid for exactly one event.

**Global users**
    Global users exist everywhere in the installation of Tixl. They can buy tickets for multiple events and they can be managers of one or more Organizers/Events. Global users are identified by e-mail addresses.

For more information about this user concept and reasons behind it, see the docstring of the ``tixlbase.models.User`` class.

