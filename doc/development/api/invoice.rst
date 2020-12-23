.. highlight:: python
   :linenothreshold: 5

Writing an invoice renderer plugin
==================================

An invoice renderer controls how invoice files are built.
The creation of such a plugin is very similar to creating an export output.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

Output registration
-------------------

The invoice renderer API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available invoice renderers. Your plugin
should listen for this signal and return the subclass of ``pretix.base.invoice.BaseInvoiceRenderer``
that we'll provide in this plugin:

.. code-block:: python

    from django.dispatch import receiver

    from pretix.base.signals import register_invoice_renderers


    @receiver(register_invoice_renderers, dispatch_uid="output_custom")
    def register_invoice_renderers(sender, **kwargs):
        from .invoice import MyInvoiceRenderer
        return MyInvoiceRenderer


The renderer class
------------------

.. class:: pretix.base.invoice.BaseInvoiceRenderer

   The central object of each invoice renderer is the subclass of ``BaseInvoiceRenderer``.

   .. py:attribute:: BaseInvoiceRenderer.event

      The default constructor sets this property to the event we are currently
      working for.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. automethod:: generate

Helper class for reportlab-base renderers
-----------------------------------------

All PDF rendering that ships with pretix is based on reportlab. We recommend to read the
`reportlab User Guide`_ to understand all the concepts used here.

If you want to implement a renderer that also uses report lab, this helper class might be
convenient to you:


.. class:: pretix.base.invoice.BaseReportlabInvoiceRenderer

   .. py:attribute:: BaseReportlabInvoiceRenderer.pagesize

   .. py:attribute:: BaseReportlabInvoiceRenderer.left_margin

   .. py:attribute:: BaseReportlabInvoiceRenderer.right_margin

   .. py:attribute:: BaseReportlabInvoiceRenderer.top_margin

   .. py:attribute:: BaseReportlabInvoiceRenderer.bottom_margin

   .. py:attribute:: BaseReportlabInvoiceRenderer.doc_template_class

   .. py:attribute:: BaseReportlabInvoiceRenderer.invoice

   .. automethod:: _init

   .. automethod:: _get_stylesheet

   .. automethod:: _register_fonts

   .. automethod:: _on_first_page

   .. automethod:: _on_other_page

   .. automethod:: _get_first_page_frames

   .. automethod:: _get_other_page_frames

   .. automethod:: _build_doc

.. _reportlab User Guide: https://www.reportlab.com/docs/reportlab-userguide.pdf
