.. highlight:: python
   :linenothreshold: 5

Plugin basics
=============

It is possible to extend pretix with custom Python code using the official plugin
API. Every plugin has to be implemented as an independent Django 'app' living
either in an own python package either installed like any python module or in 
the ``pretixplugins/`` directory of your pretix installation. A plugin may only
require two steps to install:

* Add it to the ``INSTALLED_APPS`` setting of Django in ``pretix/settings.py``
* Perform database migrations by using ``python manage.py migrate``

The communication between pretix and the plugins happens via Django's
`signal dispatcher`_ pattern. The core modules of pretix, ``pretixbase``, 
``pretixcontrol`` and ``pretixpresale`` expose a number of signals which are documented 
on the next pages.

.. _`pluginsetup`:

Creating a plugin
-----------------

To create a new plugin, create a new python package.

Inside your newly created folder, you'll probably need the three python modules ``__init__.py``,
``models.py`` and ``signals.py``, although this is up to you. You can take the following
example, taken from the time restriction module (see next chapter) as a template for your 
``__init__.py`` module::

    from django.apps import AppConfig
    from django.utils.translation import ugettext_lazy as _
    from pretix.base.plugins import PluginType


    class TimeRestrictionApp(AppConfig):
        name = 'pretix.plugins.timerestriction'
        verbose_name = _("Time restriction")

        class PretixPluginMeta:
            type = PluginType.RESTRICTION
            name = _("Restriciton by time")
            author = _("the pretix team")
            version = '1.0.0'
            description = _("This plugin adds the possibility to restrict the sale " +
                            "of a given item or variation to a certain timeframe " +
                            "or change its price during a certain period.")

        def ready(self):
            from . import signals  # NOQA

    default_app_config = 'pretix.plugins.timerestriction.TimeRestrictionApp'

.. IMPORTANT::
   You have to implement a ``PretixPluginMeta`` class like in the example to make your
   plugin available to the users.

.. _signal dispatcher: https://docs.djangoproject.com/en/1.7/topics/signals/
.. _namespace packages: http://legacy.python.org/dev/peps/pep-0420/
