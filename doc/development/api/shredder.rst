.. highlight:: python
   :linenothreshold: 5

.. _`shredder`:

Writing a data shredder
=======================

If your plugin adds the ability to store personal data within pretix, you should also implement a "data shredder"
to anonymize or pseudonymize the data later.

Shredder registration
---------------------

The data shredder API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available data shredders. Your plugin
should listen for this signal and return the subclass of ``pretix.base.shredder.BaseDataShredder``
that we'll provide in this plugin:

.. sourcecode:: python

    from django.dispatch import receiver

    from pretix.base.signals import register_data_shredders


    @receiver(register_data_shredders, dispatch_uid="custom_data_shredders")
    def register_shredder(sender, **kwargs):
        return [
            PluginDataShredder,
        ]

The shredder class
------------------

.. class:: pretix.base.shredder.BaseDataShredder

   The central object of each data shredder is the subclass of ``BaseDataShredder``.

   .. py:attribute:: BaseDataShredder.event

      The default constructor sets this property to the event we are currently
      working for.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: description

      This is an abstract attribute, you **must** override this!

   .. automethod:: generate_files

   .. automethod:: shred_data

Example
-------

For example, the core data shredder responsible for removing invoice address information including their history
looks like this:

.. sourcecode:: python

    class InvoiceAddressShredder(BaseDataShredder):
        verbose_name = _('Invoice addresses')
        identifier = 'invoice_addresses'
        description = _('This will remove all invoice addresses from orders, '
                        'as well as logged changes to them.')

        def generate_files(self) -> List[Tuple[str, str, str]]:
            yield 'invoice-addresses.json', 'application/json', json.dumps({
                ia.order.code: InvoiceAdddressSerializer(ia).data
                for ia in InvoiceAddress.objects.filter(order__event=self.event)
            }, indent=4)

        @transaction.atomic
        def shred_data(self):
            InvoiceAddress.objects.filter(order__event=self.event).delete()

            for le in self.event.logentry_set.filter(action_type="pretix.event.order.modified"):
                d = le.parsed_data
                if 'invoice_data' in d and not isinstance(d['invoice_data'], bool):
                    for field in d['invoice_data']:
                        if d['invoice_data'][field]:
                            d['invoice_data'][field] = '█'
                    le.data = json.dumps(d)
                    le.shredded = True
                    le.save(update_fields=['data', 'shredded'])

