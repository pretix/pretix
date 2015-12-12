.. highlight:: python
   :linenothreshold: 5

Data models
===========

Pretix provides the following data(base) models. Every model and every model method or field that is not
documented here is considered private and should not be used by third-party plugins, as it may change
without advance notice.

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