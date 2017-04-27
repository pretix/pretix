.. highlight:: python
   :linenothreshold: 5

Data model
==========

pretix provides the following data(base) models. Every model and every model method or field that is not
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

.. autoclass:: pretix.base.models.Event
   :members:

.. autoclass:: pretix.base.models.Team
   :members:

.. autoclass:: pretix.base.models.RequiredAction
   :members:


Items
-----

.. autoclass:: pretix.base.models.Item
   :members:

.. autoclass:: pretix.base.models.ItemCategory
   :members:

.. autoclass:: pretix.base.models.ItemVariation
   :members:

.. autoclass:: pretix.base.models.Question
   :members:

.. autoclass:: pretix.base.models.Quota
   :members:

Carts and Orders
----------------

.. autoclass:: pretix.base.models.Order
   :members:

.. autoclass:: pretix.base.models.AbstractPosition
   :members:

.. autoclass:: pretix.base.models.OrderPosition
   :members:

.. autoclass:: pretix.base.models.CartPosition
   :members:

.. autoclass:: pretix.base.models.QuestionAnswer
:members:

.. autoclass:: pretix.base.models.Checkin
   :members:

Logging
-------

.. autoclass:: pretix.base.models.LogEntry
   :members:

Invoicing
---------

.. autoclass:: pretix.base.models.Invoice
   :members:

.. autoclass:: pretix.base.models.InvoiceLine
   :members:

Vouchers
--------

.. autoclass:: pretix.base.models.Voucher
   :members:

.. _cleanerversion: https://github.com/swisscom/cleanerversion
