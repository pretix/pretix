.. highlight:: python
   :linenothreshold: 5

Plugin basics
=============

It is possible to extend tixl with custom Python code using the official plugin
API. Every plugin has to be implemented as an independent Django 'app' living
either in an own python package either installed like any python module or in 
the ``tixlplugins/`` directory of your tixl installation. A plugin may only
require two steps to install:

* Add it to the ``INSTALLED_APPS`` setting of Django in ``tixl/settings.py``
* Perform database migrations by using ``python manage.py migrate``

The communication between tixl and the plugins happens via Django's
`signal dispatcher`_ pattern. The core modules of tixl, ``tixlbase``, 
``tixlcontrol`` and ``tixlpresale`` expose a number of signals which are documented 
on the next pages.

.. _`pluginsetup`:

Creating a plugin
-----------------

To create a new plugin, create a new python package as a subpackage to ``tixlplugins``.
In order to do so, you can place your module into tixl's :file:`tixlplugins` folder *or
anywhere else in your python import path* inside a folder called ``tixlplugins``. 

.. IMPORTANT::
    This makes use of a design pattern called `namespace packages`_ which is only 
    implicitly available as of Python 3.4. As we aim to support Python 3.2 for a bit 
    longer, you **MUST** put **EXACLTY** the following content into ``tixlplugins/__init__.py``
    if you create a new ``tixlplugins`` folder somewhere in your path::
        
        from pkgutil import extend_path
        __path__ = extend_path(__path__, __name__)

    Otherwise it **will break** on Python 3.2 systems *depending on the python path's order*,
    which is not tolerable behaviour. Also, even on Python 3.4 the test runner seems to have
    problems without this workaround.


Inside your newly created folder, you'll probably need the three python modules ``__init__.py``,
``models.py`` and ``signals.py``, although this is up to you. You can take the following
example, taken from the time restriction module (see next chapter) as a template for your 
``__init__.py`` module::

    from django.apps import AppConfig


    class TimeRestrictionApp(AppConfig):
        name = 'tixlplugins.timerestriction'
        verbose_name = "Time restriction"

        def ready(self):
            from . import signals

    default_app_config = 'tixlplugins.timerestriction.TimeRestrictionApp'


.. _signal dispatcher: https://docs.djangoproject.com/en/1.7/topics/signals/
.. _namespace packages: http://legacy.python.org/dev/peps/pep-0420/
