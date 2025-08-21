.. highlight:: python
   :linenothreshold: 5

Data sync providers
===================

.. warning:: This feature is considered **experimental**. It might change at any time without prior notice.

pretix provides connectivity to many external services through plugins. A common requirement
is unidirectionally sending (order, customer, ticket, ...) data into external systems.
The transfer is usually triggered by signals provided by pretix core (e.g. :data:`order_placed`),
but performed asynchronously.

Such plugins should use the :class:`OutboundSyncProvider` API to utilize the queueing, retry and mapping 
mechanisms as well as the user interface for configuration and monitoring. Sync providers are registered 
in the :py:attr:`pretix.base.datasync.datasync.datasync_providers` :ref:`registry <registries>`.

An :class:`OutboundSyncProvider` for subscribing event participants to a mailing list could start
like this, for example:

.. code-block:: python

    from pretix.base.datasync.datasync import (OutboundSyncProvider, datasync_providers)

    @datasync_providers.register
    class MyListSyncProvider(OutboundSyncProvider):
        identifier = "my_list"
        display_name = "My Mailing List Service"
        # ...


The plugin must register listeners in `signals.py` for all signals that should to trigger a sync and
within it has to call :meth:`MyListSyncProvider.enqueue_order` to enqueue the order for synchronization:

.. code-block:: python

    @receiver(order_placed, dispatch_uid="mylist_order_placed")
    def on_order_placed(sender, order, **kwargs):
        MyListSyncProvider.enqueue_order(order, "order_placed")


Property mappings
-----------------

Most of these plugins need to translate data from some pretix objects (e.g. orders)
into an external system's data structures. Sometimes, there is only one reasonable way or the
plugin author makes an opinionated decision what information from which objects should be
transferred into which data structures in the external system.

Otherwise, you can use a :class:`PropertyMappingFormSet` to let the user set up a mapping from pretix model fields
to external data fields. You could store the mapping information either in the event settings, or in a separate
data model. Your implementation of :attr:`OutboundSyncProvider.mappings`
needs to provide a list of mappings, which can be e.g. static objects or model instances, as long as they
have at least the properties defined in
:class:`pretix.base.datasync.datasync.StaticMapping`.

.. code-block:: python

    # class MyListSyncProvider, contd.
        def mappings(self):
            return [
                StaticMapping(
                    id=1, pretix_model='Order', external_object_type='Contact',
                    pretix_id_field='email', external_id_field='email',
                    property_mappings=self.event.settings.mylist_order_mapping,
                ))
            ]


Currently, we support `orders` and `order positions` as data sources, with the data fields defined in
:func:`pretix.base.datasync.sourcefields.get_data_fields`.

To perform the actual sync, implement :func:`sync_object_with_properties` and optionally
:func:`finalize_sync_order`. The former is called for each object to be created according to the ``mappings``.
For each order that was enqueued using :func:`enqueue_order`:

- each Mapping with ``pretix_model == "Order"`` results in one call to :func:`sync_object_with_properties`,
- each Mapping with ``pretix_model == "OrderPosition"`` results in one call to
  :func:`sync_object_with_properties` per order position,
- :func:`finalize_sync_order` is called one time after all calls to :func:`sync_object_with_properties`.


Implementation examples
-----------------------

For example implementations, see the test cases in :mod:`tests.base.test_datasync`.

In :class:`SimpleOrderSync`, a basic data transfer of order data only is
shown. Therein, a ``sync_object_with_properties`` method is defined as follows:

.. code-block:: python

    from pretix.base.datasync.utils import assign_properties

    # class MyListSyncProvider, contd.
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
            old_values=pre_existing_object or {},
            is_new=pre_existing_object is None,
            list_sep=";",
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

.. note:: The result dictionaries of earlier invocations of :func:`sync_object_with_properties` are
          only provided in subsequent calls of the same sync run, such that a mapping can
          refer to e.g. the external id of an object created by a preceding mapping.
          However, the result dictionaries are currently not provided across runs. This will
          likely change in a future revision of this API, to allow easier integration of external
          systems that do not allow retrieving/updating data by a pretix-provided key.

``mapped_objects`` is a dictionary of lists of dictionaries. The keys to the dictionary are
the mapping identifiers (``mapping.id``), the lists contain the result dictionaries returned
by :func:`sync_object_with_properties`.


In :class:`OrderAndTicketAssociationSync`, an example is given where orders, order positions,
and the association between them are transferred.


The OutboundSyncProvider base class
-----------------------------------

.. autoclass:: pretix.base.datasync.datasync.OutboundSyncProvider
   :members:


Property mapping format
-----------------------

To allow the user to configure property mappings, you can use the PropertyMappingFormSet,
which will generate the required ``property_mappings`` value automatically. If you need
to specify the property mappings programmatically, you can refer to the description below
on their format.

.. autoclass:: pretix.control.forms.mapping.PropertyMappingFormSet
   :members: to_property_mappings_json

A simple JSON-serialized ``property_mappings`` list for mapping some order information can look like this:

.. code-block:: json

      [
        {
            "pretix_field": "email",
            "external_field": "orderemail",
            "value_map": "",
            "overwrite": "overwrite",
        },
        {
            "pretix_field": "order_status",
            "external_field": "status",
            "value_map": "{\"n\": \"pending\", \"p\": \"paid\", \"e\": \"expired\", \"c\": \"canceled\", \"r\": \"refunded\"}",
            "overwrite": "overwrite",
        },
        {
            "pretix_field": "order_total",
            "external_field": "total",
            "value_map": "",
            "overwrite": "overwrite",
        }
      ]


Translating mappings on Event copy
----------------------------------

Property mappings can contain references to event-specific primary keys. Therefore, plugins must register to the
event_copy_data signal and call translate_property_mappings on all property mappings they store.

.. autofunction:: pretix.base.datasync.utils.translate_property_mappings
