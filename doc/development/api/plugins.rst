.. highlight:: python
   :linenothreshold: 5

.. _`pluginsetup`:

Creating a plugin
=================

It is possible to extend pretix with custom Python code using the official plugin
API. Every plugin has to be implemented as an independent Django 'app' living
in its own python package installed like any other python module. There are also some
official plugins inside the ``pretix/plugins/`` directory of your pretix installation.

The communication between pretix and the plugins happens mostly using Django's
`signal dispatcher`_ feature. The core modules of pretix, ``pretix.base``,
``pretix.control`` and ``pretix.presale`` expose a number of signals which are documented
on the next pages.

To create a new plugin, create a new python package which must be a valid `Django app`_
and must contain plugin metadata, as described below.
There is some boilerplate that you will need for every plugin to get started. To save your
time, we created a `cookiecutter`_ template that you can use like this::

   $ pip install cookiecutter
   $ cookiecutter https://github.com/pretix/pretix-plugin-cookiecutter

This will ask you some questions and then create a project folder for your plugin.

The following pages go into detail about the several types of plugins currently
supported. While these instructions don't assume that you know a lot about pretix,
they do assume that you have prior knowledge about Django (e.g. its view layer,
how its ORM works, etc.).

Plugin metadata
---------------

The plugin metadata lives inside a ``PretixPluginMeta`` class inside your app's
configuration class. The metadata class must define the following attributes:

.. rst-class:: rest-resource-table

================== ==================== ===========================================================
Attribute          Type                 Description
================== ==================== ===========================================================
name               string               The human-readable name of your plugin
author             string               Your name
version            string               A human-readable version code of your plugin
description        string               A more verbose description of what your plugin does. May contain HTML.
category           string               Category of a plugin. Either one of ``"FEATURE"``, ``"PAYMENT"``,
                                        ``"INTEGRATION"``, ``"CUSTOMIZATION"``, ``"FORMAT"``, or ``"API"``,
                                        or any other string.
picture            string (optional)    Path to a picture resolvable through the static file system.
featured           boolean (optional)   ``False`` by default, can promote a plugin if it's something many users will want, use carefully.
visible            boolean (optional)   ``True`` by default, can hide a plugin so it cannot be normally activated.
restricted         boolean (optional)   ``False`` by default, restricts a plugin such that it can only be enabled
                                        for an event by system administrators / superusers.
experimental       boolean (optional)   ``False`` by default, marks a plugin as an experimental feature in the plugins list.
compatibility      string               Specifier for compatible pretix versions.
level              string               System level the plugin can be activated at.
                                        Set to ``pretix.base.plugins.PLUGIN_LEVEL_EVENT`` for plugins that can be activated
                                        at event level and then be active for that event only.
                                        Set to ``pretix.base.plugins.PLUGIN_LEVEL_ORGANIZER`` for plugins that can be
                                        activated only for the organizer as a whole and are active for any event within
                                        that organizer.
                                        Set to ``pretix.base.plugins.PLUGIN_LEVEL_EVENT_ORGANIZER_HYBRID`` for plugins that
                                        can be activated at organizer level but are considered active only within events
                                        for which they have also been specifically activated.
                                        More levels, e.g. user-level plugins, might be invented in the future.
settings_links     list                 List of ``((menu name, submenu name, …), urlname, url_kwargs)`` tuples that point
                                        to the plugin's settings.
navigation_links   list                 List of ``((menu name, submenu name, …), urlname, url_kwargs)`` tuples that point
                                        to the plugin's system pages.
================== ==================== ===========================================================

A working example would be:

.. code-block:: python

    try:
        from pretix.base.plugins import PluginConfig, PLUGIN_LEVEL_EVENT
    except ImportError:
        raise RuntimeError("Please use pretix 2025.7 or above to run this plugin!")
    from django.utils.translation import gettext_lazy as _


    class PaypalApp(PluginConfig):
        name = 'pretix_paypal'
        verbose_name = _("PayPal")

        class PretixPluginMeta:
            name = _("PayPal")
            author = _("the pretix team")
            version = '1.0.0'
            category = 'PAYMENT'
            picture = 'pretix_paypal/paypal_logo.svg'
            level = PLUGIN_LEVEL_EVENT
            visible = True
            featured = False
            restricted = False
            description = _("This plugin allows you to receive payments via PayPal")
            compatibility = "pretix>=2.7.0"
            settings_links = []
            navigation_links = []


    default_app_config = 'pretix_paypal.PaypalApp'

The ``AppConfig`` class may implement a property ``compatibility_errors``, that checks
whether the pretix installation meets all requirements of the plugin. If so,
it should contain ``None`` or an empty list, otherwise a list of strings containing
human-readable error messages. We recommend using the ``django.utils.functional.cached_property``
decorator, as it might get called a lot. You can also implement ``compatibility_warnings``,
those will be displayed but not block the plugin execution.

The ``AppConfig`` class may implement a method ``is_available(event)`` that checks if a plugin
is available for a specific event. If not, it will not be shown in the plugin list of that event.
You should not define ``is_available`` and ``restricted`` on the same plugin.

Plugin registration
-------------------

Somehow, pretix needs to know that your plugin exists at all. For this purpose, we
make use of the `entry point`_ feature of setuptools. To register a plugin that lives
in a separate python package, your ``setup.py`` should contain something like this:

.. code-block:: python

    setup(
        args...,
        entry_points="""
    [pretix.plugin]
    pretix_paypal=pretix_paypal:PretixPluginMeta
    """
    )


This will automatically make pretix discover this plugin as soon as it is installed e.g.
through ``pip``. During development, you can just run ``python setup.py develop`` inside
your plugin source directory to make it discoverable.

.. _`signals`:
Signals
-------

The various components of pretix define a number of signals which your plugin can
listen for. We will go into the details of the different signals in the following
pages. We suggest that you put your signal receivers into a ``signals`` submodule
of your plugin. You should extend your ``AppConfig`` (see above) by the following
method to make your receivers available:

.. code-block:: python

    class PaypalApp(AppConfig):
        …

        def ready(self):
            from . import signals  # NOQA

You can optionally specify code that is executed when your plugin is activated for an event
or organizer in the ``installed`` method:

.. code-block:: python

    class PaypalApp(AppConfig):
        …

        def installed(self, event_or_organizer):
            pass  # Your code here


Note that ``installed`` will *not* be called if the plugin is indirectly activated for an event
because the event is created with settings copied from another event.

.. _`registries`:
Registries
----------

Many signals in pretix are used so that plugins can "register" a class, e.g. a payment provider or a
ticket renderer.

However, for some of them (types of :ref:`Log Entries <logging>`) we use a different method to keep track of them:
In a ``Registry``, classes are collected at application startup, along with a unique key (in case
of LogEntryType, the ``action_type``) as well as which plugin registered them.

To register a class, you can use one of several decorators provided by the Registry object:

.. autoclass:: pretix.base.logentrytypes.LogEntryTypeRegistry
   :members: register, new, new_from_dict

All files in which classes are registered need to be imported in the ``AppConfig.ready`` as explained
in `Signals <signals>`_ above.

Views
-----

Your plugin may define custom views. If you put an ``urls`` submodule into your
plugin module, pretix will automatically import it and include it into the root
URL configuration with the namespace ``plugins:<label>:``, where ``<label>`` is
your Django app label.

.. WARNING:: If you define custom URLs and views, you are currently on your own
   with checking that the calling user is logged in, has appropriate permissions,
   etc. We plan on providing native support for this in a later version.

To make your plugin views easily discoverable, you can specify links for "Go to"
and "Settings" buttons next to your entry on the plugin page. These links should be
added to the ``navigation_links`` and ``settings_links``, respectively, in the
``PretixPluginMeta`` class.

Each array entry consists of a tuple ``(label, urlname, kwargs)``. For the label,
either a string or a tuple of strings can be specified. In the latter case, the provided
strings will be merged with a separator indicating they are successive navigation steps
the user would need to take to reach the page via the regular menu
(e.g. "Payment > Bank transfer" as below).

.. code-block:: python

        settings_links = [
            ((_("Payment"), _("Bank transfer")), "control:event.settings.payment.provider", {"provider": "banktransfer"}),
        ]
        navigation_links = [
            ((_("Bank transfer"), _("Import bank data")), "plugins:banktransfer:import", {}),
            ((_("Bank transfer"), _("Export refunds")), "plugins:banktransfer:refunds.list", {}),
        ]


.. _Django app: https://docs.djangoproject.com/en/3.0/ref/applications/
.. _signal dispatcher: https://docs.djangoproject.com/en/3.0/topics/signals/
.. _namespace packages: https://legacy.python.org/dev/peps/pep-0420/
.. _entry point: https://setuptools.readthedocs.io/en/latest/pkg_resources.html#locating-plugins
.. _cookiecutter: https://cookiecutter.readthedocs.io/en/latest/
