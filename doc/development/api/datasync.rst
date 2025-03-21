.. highlight:: python
   :linenothreshold: 5

Data sync providers
===================

Pretix provides connectivity to many external services through plugins. A common requirement
is unidirectionally sending (order, customer, ticket, ...) data into external systems.
The transfer is usually triggered by signals provided by pretix core (e.g. order_created),
but performed asynchronously.

Such plugins should use the :class:`OutboundSyncProvider` API to utilize the queueing, retry and mapping mechanisms as well as the user interface for configuration and monitoring.

An :class:`OutboundSyncProvider` for registering event participants in a mailing list could start
like this, for example:

.. code-block:: python

    class MyListSyncProvider(OutboundSyncProvider):
        identifier = "my_list"
        # ...



The plugin must register listeners in `signals.py` for all signals that should to trigger a sync and
within it has to call `MyListSyncProvider.enqueue_order` to enqueue the order for synchronization:

.. code-block:: python

    @receiver(order_placed, dispatch_uid="mylist_order_placed")
    def on_order_placed(sender, order, **kwargs):
        MyListSyncProvider.enqueue_order(order, "order_placed")




Furthermore, most of these plugins need to transfer data from some pretix objects (e.g. orders)
into an external systems' data structures. Sometimes, there is only one reasonable way or the
plugin author makes an opinionated decision what information from which objects should be
transferred into which data structures in the external system.

Otherwise, you can use a `PropertyMappingFormSet` to let the user set up a mapping from pretix model fields
to external data fields. You could store the mapping information either in the Event settings, or in a separate
data model. Your implementation of OutboundSyncProvider.mappings needs to provide a list of Mappings, with at least
the properties defined in :class:`pretix.base.datasync.datasync.StaticMapping`.

.. code-block:: python

    # class MyListSyncProvider, contd.
        def mappings(self):
            return [
                StaticMapping(1, 'Order', 'Contact', 'email', 'email',
                              self.event.settings.mylist_order_mapping))
            ]


Currently, we support Orders and OrderPositions as data sources, with the data fields defined in
:func:`pretix.base.datasync.sourcefields.get_data_fields`.



