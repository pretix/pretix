.. highlight:: python
   :linenothreshold: 5

Writing an exporter plugin
==========================

An Exporter is a method to export the product and order data in pretix for later use in another
program.

In this document, we will walk through the creation of an exporter output plugin step by step.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

Exporter registration
---------------------

The exporter API does not make a lot of usage from signals, however, it does use a signal to get a list of
all available exporters. Your plugin should listen for this signal and return the subclass of
``pretix.base.exporter.BaseExporter``
that we'll provide in this plugin:

.. code-block:: python

    from django.dispatch import receiver

    from pretix.base.signals import register_data_exporters


    @receiver(register_data_exporters, dispatch_uid="exporter_myexporter")
    def register_data_exporter(sender, **kwargs):
        from .exporter import MyExporter
        return MyExporter

Some exporters might also prove to be useful, when provided on an organizer-level. In order to declare your
exporter as capable of providing exports spanning multiple events, your plugin should listen for this signal
and return the subclass of ``pretix.base.exporter.BaseExporter`` that we'll provide in this plugin:

.. code-block:: python

    from django.dispatch import receiver

    from pretix.base.signals import register_multievent_data_exporters


    @receiver(register_multievent_data_exporters, dispatch_uid="multieventexporter_myexporter")
    def register_multievent_data_exporter(sender, **kwargs):
        from .exporter import MyExporter
        return MyExporter

If your exporter supports both event-level and multi-event level exports, you will need to listen for both
signals.

The exporter class
------------------

.. class:: pretix.base.exporter.BaseExporter

   The central object of each exporter is the subclass of ``BaseExporter``.

   .. py:attribute:: BaseExporter.event

      The default constructor sets this property to the event we are currently
      working for.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: export_form_fields

   .. automethod:: render

      This is an abstract method, you **must** override this!
