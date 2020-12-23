.. highlight:: python
   :linenothreshold: 5

Writing an HTML e-mail renderer plugin
======================================

An email renderer class controls how the HTML part of e-mails sent by pretix is built.
The creation of such a plugin is very similar to creating an export output.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

Output registration
-------------------

The email HTML renderer API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available email renderers. Your plugin
should listen for this signal and return the subclass of ``pretix.base.email.BaseHTMLMailRenderer``
that we'll provide in this plugin:

.. code-block:: python

    from django.dispatch import receiver

    from pretix.base.signals import register_html_mail_renderers


    @receiver(register_html_mail_renderers, dispatch_uid="renderer_custom")
    def register_mail_renderers(sender, **kwargs):
        from .email import MyMailRenderer
        return MyMailRenderer


The renderer class
------------------

.. class:: pretix.base.email.BaseHTMLMailRenderer

   The central object of each email renderer is the subclass of ``BaseHTMLMailRenderer``.

   .. py:attribute:: BaseHTMLMailRenderer.event

      The default constructor sets this property to the event we are currently
      working for.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: thumbnail_filename

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: is_available

   .. automethod:: render

      This is an abstract method, you **must** implement this!

Helper class for template-base renderers
----------------------------------------

The email renderer that ships with pretix is based on Django templates to generate HTML.
In case you also want to render emails based on a template, we provided a ready-made base
class ``TemplateBasedMailRenderer`` that you can re-use to perform the following steps:

* Convert the body text and the signature to HTML using our markdown renderer

* Render the template

* Call `inlinestyler`_ to convert all ``<style>`` style sheets to inline ``style=""``
  attributes for better compatibility

To use it, you just need to implement some variables:

.. code-block:: python

    class ClassicMailRenderer(TemplateBasedMailRenderer):
        verbose_name = _('pretix default')
        identifier = 'classic'
        thumbnail_filename = 'pretixbase/email/thumb.png'
        template_name = 'pretixbase/email/plainwrapper.html'

The template is passed the following context variables:

``site``
   Name of the pretix installation (``settings.PRETIX_INSTANCE_NAME``)

``site_url``
   Root URL of the pretix installation (``settings.SITE_URL``)

``body``
   The body as markdown (render with ``{{ body|safe }}``)

``subject``
   The email subject

``color``
   The primary color of the event

``event``
   The ``Event`` object

``signature`` (optional, only if configured)
   The signature with event organizer contact details as markdown (render with ``{{ signature|safe }}``)

``order`` (optional, only if applicable)
   The ``Order`` object

``position`` (optional, only if applicable)
   The ``OrderPosition`` object

.. _inlinestyler: https://pypi.org/project/inlinestyler/
