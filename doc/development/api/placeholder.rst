.. highlight:: python
   :linenothreshold: 5

Writing a template placeholder plugin
=====================================

A template placeholder is a dynamic value that pretix users can use in their email templates and in other
configurable texts.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

Placeholder registration
------------------------

The placeholder API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available placeholders. Your plugin
should listen for this signal and return an instance of a subclass of ``pretix.base.services.placeholders.BaseTextPlaceholder``:

.. code-block:: python

    from django.dispatch import receiver

    from pretix.base.signals import register_text_placeholders


    @receiver(register_text_placeholders, dispatch_uid="placeholder_custom")
    def register_placeholder_renderers(sender, **kwargs):
        from .placeholders import MyPlaceholderClass
        return MyPlaceholder()


Context mechanism
-----------------

Templates are used in different "contexts" within pretix. For example, many emails are rendered from
templates in the context of an order, but some are not, such as the notification of a waiting list voucher.

Not all placeholders make sense everywhere, and placeholders usually depend on some parameters
themselves, such as the ``Order`` object. Therefore, placeholders are expected to explicitly declare
what values they depend on and they will only be available in a context where all those dependencies are
met. Currently, placeholders can depend on the following context parameters:

* ``event``
* ``order``
* ``position``
* ``waiting_list_entry``
* ``invoice_address``
* ``payment``

There are a few more that are only to be used internally but not by plugins.

The placeholder class
---------------------

.. class:: pretix.base.services.placeholders.BaseTextPlaceholder

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: required_context

      This is an abstract attribute, you **must** override this!

   .. automethod:: render

      This is an abstract method, you **must** implement this!

   .. automethod:: render_sample

      This is an abstract method, you **must** implement this!

Helper class for simple placeholders
------------------------------------

pretix ships with a helper class that makes it easy to provide placeholders based on simple
functions:

.. code-block:: python

     placeholder = SimpleFunctionalTextPlaceholder(
         'code', ['order'], lambda order: order.code, sample='F8VVL'
     )

Signals
-------

.. automodule:: pretix.base.signals
   :no-index:
   :members: register_text_placeholders

.. automodule:: pretix.base.signals
   :no-index:
   :members: register_mail_placeholders

