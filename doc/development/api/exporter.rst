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
      working for. This will be ``None`` if the exporter is run for multiple
      events.

   .. py:attribute:: BaseExporter.events

      The default constructor sets this property to the list of events to work
      on, regardless of whether the exporter is called for one or multiple events.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: description

   .. autoattribute:: category

   .. autoattribute:: feature

   .. autoattribute:: export_form_fields

   .. autoattribute:: repeatable_read

   .. automethod:: render

      This is an abstract method, you **must** override this!

   .. automethod:: available_for_user

   .. automethod:: get_required_event_permission

On organizer level, by default exporters are expected to handle on a *set of events* and the system will automatically
add a form field that allows the selection of events, limited to events the user has correct permissions for. If this
does not fit your organizer, because it is not related to events, you should **also** inherit from the following class:

.. class:: pretix.base.exporter.OrganizerLevelExportMixin

   .. automethod:: get_required_organizer_permission
