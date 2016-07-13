.. highlight:: python
   :linenothreshold: 5

Writing an exporter plugin
==========================

An Exporter is a method to export the product and order data in pretix for later use in another
context.

In this document, we will walk through the creation of an exporter output plugin. This
is very similar to creating a payment provider.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

Exporter registration
---------------------

The exporter API does not make a lot of usage from signals, however, it does use a signal to get a list of
all available exporters. Your plugin should listen for this signal and return the subclass of
``pretix.base.exporter.BaseExporter``
that we'll provide in this plugin::

    from django.dispatch import receiver

    from pretix.base.signals import register_data_exporter


    @receiver(register_data_exporter, dispatch_uid="exporter_myexporter")
    def register_data_exporter(sender, **kwargs):
        from .exporter import MyExporter
        return MyExporter


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
