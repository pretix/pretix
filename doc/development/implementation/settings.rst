Settings storage
================

pretix is highly configurable and therefore needs to store a lot of per-event and per-organizer settings.
For this purpose, we use `django-hierarkey`_ which started out as part of pretix and then got refactored into
its own library. It has a comprehensive `documentation`_ which you should read if you work with settings in pretix.

The settings are stored in the database and accessed through a ``HierarkeyProxy`` instance. You can obtain
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
See the hierarkey `documentation`_ for more information.

To avoid naming conflicts, plugins are requested to prefix all settings they use with the name of the plugin
or something unique, e.g. ``payment_paypal_api_key``. To reduce redundant typing of this prefix, we provide
another helper class:

.. autoclass:: pretix.base.settings.SettingsSandbox

When implementing e.g. a payment or export provider, you do not event need to create this sandbox yourself,
you will just be passed a sandbox object with a prefix generated from your provider name.

Forms
-----

Hierarkey also provides a base class for forms that allow the modification of settings. pretix contains a
subclass that also adds support for internationalized fields:

.. autoclass:: pretix.base.forms.SettingsForm

You can simply use it like this:

.. code-block:: python

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

Defaults in plugins
-------------------

Plugins can add custom hardcoded defaults in the following way:

.. code-block:: python

    from pretix.base.settings import settings_hierarkey

    settings_hierarkey.add_default('key', 'value', type)

Make sure that you include this code in a module that is imported at app loading time.

.. _django-hierarkey: https://github.com/raphaelm/django-hierarkey
.. _documentation: https://django-hierarkey.readthedocs.io/en/latest/
