.. highlight:: python
   :linenothreshold: 5

Writing an invoice transmission plugin
======================================

An invoice transmission provider transports an invoice from the sender to the recipient.
There are pre-defined types of invoice transmission in pretix, currently ``"email"``, ``"peppol"``, and ``"it_sdi"``.
You can find more information about them at :ref:`rest-transmission-types`.

New transmission types can not be added by plugins but need to be added to pretix itself.
However, plugins can provide implementations for the actual transmission.
Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

Output registration
-------------------

New invoice transmission providers can be registered through the :ref:`registry <registries>` mechanism

.. code-block:: python

   from pretix.base.invoicing.transmission import transmission_providers, TransmissionProvider

   @transmission_providers.new()
   class SdiTransmissionProvider(TransmissionProvider):
       identifier = "fatturapa_providerabc"
       type = "it_sdi"
       verbose_name = _("FatturaPA through provider ABC")
       ...


The provider class
------------------

.. class:: pretix.base.invoicing.transmission.TransmissionProvider

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: type

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: priority

   .. autoattribute:: testmode_supported

   .. automethod:: is_ready

      This is an abstract method, you **must** override this!

   .. automethod:: is_available

      This is an abstract method, you **must** override this!

   .. automethod:: transmit

      This is an abstract method, you **must** override this!

   .. automethod:: settings_url
