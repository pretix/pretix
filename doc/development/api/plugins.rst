.. highlight:: python
   :linenothreshold: 5

Plugin basics
=============

It is possible to extend pretix with custom Python code using the official plugin
API. Every plugin has to be implemented as an independent Django 'app' living
in an own python package nstalled like any other python module. There are also some
official plugins inside the ``pretix/plugins/`` directory of your pretix installation.

The communication between pretix and the plugins happens mostly using Django's
`signal dispatcher`_ feature. The core modules of pretix, ``pretix.base``,
``pretix.control`` and ``pretix.presale`` expose a number of signals which are documented
on the next pages.

.. _`pluginsetup`:

To create a new plugin, create a new python package which must be a vaild `Django app`_
and must contain plugin metadata, as described below.

The following pages go into detail about the several types of plugins currently
supported. While these instructions don't assume that you know a lot about pretix,
they do assume that you have prior knowledge about Django (e.g. it's view layer,
how it's ORM works, etc.).

Plugin metadata
---------------

The plugin metadata lives inside a ``PretixPluginMeta`` class inside your app's
configuration class. The metadata class must define the following attributes:

``type`` (``pretix.base.plugins.PluginType``):
    The type of plugin. Currently available: ``RESTRICTION``, ``PAYMENT``,
    ``ADMINFEATURE``

``name`` (``str``):
    The human-readable name of your plugin

``author`` (``str``):
    Your name

``version`` (``str``):
    A human-readable version code of your plugin

``description`` (``str``):
    A more verbose description of what your plugin does.

A working example would be::

    # file: pretix/plugins/timerestriction/__init__.py
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


    default_app_config = 'pretix.plugins.timerestriction.TimeRestrictionApp'


The ``AppConfig`` class may implement a property ``compatiblity_errors``, that checks
whether the pretix installation meets all requirements of the plugin. If so,
it should contain ``None`` or an empty list, otherwise a list of strings containing
human-readable error messages. We recommend using the ``django.utils.functional.cached_property``
decorator, as it might get called a lot. You can also implement ``compatibility_warnings``,
those will be displayed but not block the plugin execution.

Plugin registration
-------------------

Somehow, pretix needs to know that your plugin exists at all. For this purpose, we
make use of the `entry point`_ feature of setuptools. To register a plugin that lives
in a seperate python package, your ``setup.py`` sould contain something like this::

    setup(
        …

        entry_points="""
    [pretix.plugin]
    sampleplugin=sampleplugin:PretixPluginMeta
    """
    )


This will automatically make pretix discover this plugin as soon as it is installed e.g.
through ``pip``. During development, you can just run ``python setup.py develop`` inside
your plugin source directory to make it discoverable.

Signals
-------

The various components of pretix define a number of signals which your plugin can
listen for. We will go into the details of the different signals in the following
pages. We suggest that you put your signal receivers into a ``signals`` submodule
of your plugin. You should extend your ``AppConfig`` (see above) by the following
method to make your receivers available::

    class TimeRestrictionApp(AppConfig):
        …

        def ready(self):
            from . import signals  # NOQA

Views
-----

Your plugin may define custom views. If you put an ``urls`` submodule into your
plugin module, pretix will automatically import it and include it into the root
URL configuration with the namespace ``plugins:<label>:``, where ``<label>`` is
your Django app label.

.. WARNING:: If you define custom URLs and views, you are currently on your own
   with checking that the calling user is logged in, has appropriate permissions,
   etc. We plan on providing native support for this in a later version.

.. _Django app: https://docs.djangoproject.com/en/1.7/ref/applications/
.. _signal dispatcher: https://docs.djangoproject.com/en/1.7/topics/signals/
.. _namespace packages: http://legacy.python.org/dev/peps/pep-0420/
.. _entry point: https://pythonhosted.org/setuptools/setuptools.html#dynamic-discovery-of-services-and-plugins