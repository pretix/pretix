.. highlight:: python
   :linenothreshold: 5

Data models
===========

Pretix provides the following data(base) models. Every model and every model method or field that is not
documented here is considered private and should not be used by third-party plugins, as it may change
without advance notice.

.. IMPORTANT::
   pretix's models are built with `cleanerversion`_, which extends the default Django ORM by adding versioning
   information to the database. There are basically three things you absolutely need to know about cleanerversion:

   * When querying the database, make sure you only get the current versions::

        queryset = Model.objects.current.filter(…)

   * Before you modify an object, clone it::

        obj = Model.objects.current.get(identity=1)  # Prefer identities over primary keys
        obj = obj.clone()  # Saves the old version to the database and creates the new one
        obj.foo = 'bar'
        obj.save()

   * Beware of batch operations, use ``queryset.update()``, ``queryset.delete()`` etc. only if
     you know what you're doing.

   There is one exception: The ``User`` model is a classic Django model!

User model
----------

.. autoclass:: pretix.base.models.User
   :members:

Organizers and events
---------------------

.. autoclass:: pretix.base.models.Organizer
   :members:

.. autoclass:: pretix.base.models.OrganizerPermission
   :members:

.. autoclass:: pretix.base.models.Event
   :members:

.. autoclass:: pretix.base.models.EventPermission
   :members:


Items
-----

.. autoclass:: pretix.base.models.Item
   :members:

.. autoclass:: pretix.base.models.ItemCategory
   :members:

.. autoclass:: pretix.base.models.Property
   :members:

.. autoclass:: pretix.base.models.PropertyValue
   :members:

.. autoclass:: pretix.base.models.Question
   :members:

.. autoclass:: pretix.base.models.ItemVariation
   :members:
   :exclude-members: add_values_from_string

.. autoclass:: pretix.base.models.Quota
   :members:

Carts and Orders
----------------

.. autoclass:: pretix.base.models.Order
   :members:

.. autoclass:: pretix.base.models.OrderPosition
   :members:

.. autoclass:: pretix.base.models.CartPosition
   :members:

.. autoclass:: pretix.base.models.QuestionAnswer
   :members:

.. _cleanerversion: https://github.com/swisscom/cleanerversion