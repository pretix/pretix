.. highlight:: python
   :linenothreshold: 5

Writing a ticket output plugin
==============================

A ticket output is a method to offer a ticket (an order) for the user to download.

In this document, we will walk through the creation of a ticket output plugin. This
is very similar to creating an export output.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

Output registration
-------------------

The ticket output API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available ticket outputs. Your plugin
should listen for this signal and return the subclass of ``pretix.base.ticketoutput.BaseTicketOutput``
that we'll provide in this plugin::

    from django.dispatch import receiver

    from pretix.base.signals import register_ticket_outputs


    @receiver(register_ticket_outputs, dispatch_uid="output_pdf")
    def register_ticket_output(sender, **kwargs):
        from .ticketoutput import PdfTicketOutput
        return PdfTicketOutput


The output class
----------------

.. class:: pretix.base.ticketoutput.BaseTicketOutput

   The central object of each ticket output is the subclass of ``BaseTicketOutput``.

   .. py:attribute:: BaseTicketOutput.event

      The default constructor sets this property to the event we are currently
      working for.

   .. py:attribute:: BaseTicketOutput.settings

      The default constructor sets this property to a ``SettingsSandbox`` object. You can
      use this object to store settings using its ``get`` and ``set`` methods. All settings
      you store are transparently prefixed, so you get your very own settings namespace.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: is_enabled

   .. autoattribute:: multi_download_enabled

   .. autoattribute:: settings_form_fields

   .. automethod:: settings_content_render

   .. automethod:: generate

   .. automethod:: generate_order

   .. autoattribute:: download_button_text

   .. autoattribute:: download_button_icon

   .. autoattribute:: preview_allowed

   .. autoattribute:: is_downloadable

   .. autoattribute:: download_action