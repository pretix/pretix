.. highlight:: python
   :linenothreshold: 5

.. spelling:: answ contrib

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
   :members: get_date_from_display, get_time_from_display, get_date_to_display, get_date_range_display, presale_has_ended, presale_is_running, cache, lock, get_plugins, get_mail_backend, payment_term_last, get_payment_providers, get_invoice_renderers, invoice_renderer, settings

.. autoclass:: pretix.base.models.SubEvent
   :members: get_date_from_display, get_time_from_display, get_date_to_display, get_date_range_display, presale_has_ended, presale_is_running

.. autoclass:: pretix.base.models.Team
   :members:

.. autoclass:: pretix.base.models.TeamAPIToken
   :members:

.. autoclass:: pretix.base.models.RequiredAction
   :members:

.. autoclass:: pretix.base.models.EventMetaProperty
   :members:

.. autoclass:: pretix.base.models.EventMetaValue
   :members:

.. autoclass:: pretix.base.models.SubEventMetaValue
   :members:


Items
-----

.. autoclass:: pretix.base.models.Item
   :members:

.. autoclass:: pretix.base.models.ItemCategory
   :members:

.. autoclass:: pretix.base.models.ItemVariation
   :members:

.. autoclass:: pretix.base.models.SubEventItem
  :members:

.. autoclass:: pretix.base.models.SubEventItemVariation
   :members:

.. autoclass:: pretix.base.models.ItemAddOn
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

.. autoclass:: pretix.base.models.OrderFee
   :members:

.. autoclass:: pretix.base.models.OrderPayment
   :members:

.. autoclass:: pretix.base.models.OrderRefund
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
