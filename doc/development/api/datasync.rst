.. highlight:: python
   :linenothreshold: 5

Data sync providers
===================

pretix provides connectivity to many external services through plugins. A common requirement
is unidirectionally sending (order, customer, ticket, ...) data into external systems.
The transfer is usually triggered by signals provided by pretix core (e.g. ``order_created``),
but performed asynchronously.

Such plugins should use the :class:`OutboundSyncProvider` API to utilize the queueing, retry and mapping mechanisms as well as the user interface for configuration and monitoring.

An :class:`OutboundSyncProvider` for registering event participants in a mailing list could start
like this, for example:

.. code-block:: python

    from pretix.base.datasync.datasync import OutboundSyncProvider

    class MyListSyncProvider(OutboundSyncProvider):
        identifier = "my_list"
        display_name = "My Mailing List Service"
        # ...


The plugin must register listeners in `signals.py` for all signals that should to trigger a sync and
within it has to call `MyListSyncProvider.enqueue_order` to enqueue the order for synchronization:

.. code-block:: python

    @receiver(order_placed, dispatch_uid="mylist_order_placed")
    def on_order_placed(sender, order, **kwargs):
        MyListSyncProvider.enqueue_order(order, "order_placed")


Furthermore, most of these plugins need to translate data from some pretix objects (e.g. orders)
into an external systems' data structures. Sometimes, there is only one reasonable way or the
plugin author makes an opinionated decision what information from which objects should be
transferred into which data structures in the external system.

Otherwise, you can use a ``PropertyMappingFormSet`` to let the user set up a mapping from pretix model fields
to external data fields. You could store the mapping information either in the event settings, or in a separate
data model. Your implementation of :func:`OutboundSyncProvider.mappings`
needs to provide a list of mappings, with at least the properties defined in
:class:`pretix.base.datasync.datasync.StaticMapping`.

.. code-block:: python

    # class MyListSyncProvider, contd.
        def mappings(self):
            return [
                StaticMapping(1, 'Order', 'Contact', 'email', 'email',
                              self.event.settings.mylist_order_mapping))
            ]


Currently, we support ``Order`` and ``OrderPosition`` as data sources, with the data fields defined in
:func:`pretix.base.datasync.sourcefields.get_data_fields`.

To perform the actual sync, implement ``sync_object_with_properties`` and optionally
``finalize_sync_order``. The former is called for each object to be created, according to the ``mappings``:
For each order that was enqueued using ``enqueue_order``:

- each Mapping with ``pretix_model == "Order"`` results in one call to `sync_object_with_properties`,
- each Mapping with ``pretix_model == "OrderPosition"`` results in one call to
  ``sync_object_with_properties`` per order position,
- ``finalize_sync_order`` is called one time after all calls to ``sync_object_with_properties``.


For example implementations, see the test cases in :package:``tests.base.test_datasync``.
In :class:`SimpleOrderSync`, a basic data transfer of order data only is
shown. Therein, a ``sync_object_with_properties`` method is defined like as follows:

.. code-block:: python

    def sync_object_with_properties(
            self, external_id_field, id_value, properties: list, inputs: dict,
            mapping, mapped_objects: dict, **kwargs,
    ):
        # First, we query the external service if our object-to-sync already exists there.
        # This is necessary to make sure our method is idempotent, i.e. handles already synced
        # data gracefully.
        pre_existing_object = self.fake_api_client.retrieve_object(
            mapping.external_object_type,
            external_id_field,
            id_value
        )

        # We use the helper function ``assign_properties`` to update a pre-existing object.
        update_values = assign_properties(
            new_values=properties,
            old_vlaues=pre_existing_object or {},
            is_new=pre_existing_object is None
        )

        # Then we can send our new data to the external service. The specifics of course depends
        # on your API, e.g. you may need to use different endpoints for creating or updating an
        # object, or pass the identifier separately instead of in the same dictionary as the
        # other properties.
        result = self.fake_api_client.create_or_update_object(mapping.external_object_type, {
            **update_values,
            external_id_field: id_value,
            "_id": pre_existing_object and pre_existing_object.get("_id"),
        })

        # Finally, return a dictionary containing at least `object_type`, `external_id_field`,
        # `id_value`, `external_link_href`, and `external_link_display_name` keys.
        # Further keys may be provided for your internal use. This dictionary is provided
        # in following calls in the ``mapped_objects`` dict, to allow creating associations
        # to this object.
        return {
            "object_type": mapping.external_object_type,
            "external_id_field": external_id_field,
            "id_value": id_value,
            "external_link_href": f"https://example.org/external-system/{mapping.external_object_type}/{id_value}/",
            "external_link_display_name": f"Contact #{id_value} - Jane Doe",
            "my_result": result,
        }


In :class:`OrderAndTicketAssociationSync`, an example is given where orders, order positions,
and the association between them are transferred.


.. autoclass:: pretix.base.datasync.datasync.OutboundSyncProvider
   :members: