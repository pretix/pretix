Settings storage
================

pretix is highly configurable and therefore needs to store a lot of per-event and per-organizer settings.
Those settings are stored in the database and accessed through a ``SettingsProxy`` instance. You can obtain
such an instance from any event or organizer model instance by just accessing ``event.settings`` or
``organizer.settings``, respectively.

Any setting consists of a key and a value. By default, all settings are strings, but the settings system
includes serializers for serializing the following types:

* Built-in types: ``int``, ``float``, ``decimal.Decimal``, ``dict``, ``list``, ``bool``
* ``datetime.date``, ``datetime.datetime``, ``datetime.time``
* ``LazyI18nString``
* References to Django ``File`` objects that are already stored in a storage backend
* References to model instances

In code, we recommend to always use the ``.get()`` method on the settings object to access a value, but for
convenience in templates you can also access settings values at ``settings[name]`` and ``settings.name``.

.. autoclass:: pretix.base.settings.SettingsProxy
   :members: get, set, delete, freeze

To avoid naming conflicts, plugins are requested to prefix all settings they use with the name of the plugin
or something unique, e.g. ``payment.paypal.api_key``. To reduce redundant typing of this prefix, we provide
another helper class:

.. autoclass:: pretix.base.settings.SettingsSandbox

When implementing e.g. a payment or export provider, you do not event need to create this sandbox yourself,
you will just be passed a sandbox object with a prefix generated from your provider name.

Forms
-----

We also provide a base class for forms that allow the modification of settings:

.. autoclass:: pretix.base.forms.SettingsForm
   :members: save

You can simply use it like this::

   class EventSettingsForm(SettingsForm):
       show_date_to = forms.BooleanField(
           label=_("Show event end date"),
           help_text=_("If disabled, only event's start date will be displayed to the public."),
           required=False
       )
       payment_term_days = forms.IntegerField(
           label=_('Payment term in days'),
           help_text=_("The number of days after placing an order the user has to pay to "
                       "preserve his reservation."),
       )
