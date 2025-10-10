#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import json
from collections import defaultdict, namedtuple
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.datasync.datasync import (
    OutboundSyncProvider, StaticMapping, datasync_providers,
)
from pretix.base.datasync.utils import assign_properties
from pretix.base.models import (
    Event, InvoiceAddress, Item, Order, Organizer, Question,
)
from pretix.base.models.datasync import (
    MODE_APPEND_LIST, MODE_OVERWRITE, MODE_SET_IF_EMPTY, MODE_SET_IF_NEW,
)
from pretix.base.services.datasync import sync_all


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer,testplugin'
    )
    event.settings.name_scheme = 'given_family'
    with scope(organizer=o):
        ticket = Item.objects.create(event=event, name='Early-bird ticket',
                                     default_price=Decimal('23.00'), admission=True)
        question = ticket.questions.create(question="Whats's your favourite colour?", type=Question.TYPE_STRING,
                                           event=event, required=False, identifier="FAV_COLOR")
        question2 = ticket.questions.create(question="Food preference", type=Question.TYPE_CHOICE,
                                            event=event, required=False, identifier="FOOD_PREF")
        option1 = question2.options.create(identifier="F1", answer="vegetarian")
        option2 = question2.options.create(identifier="F2", answer="vegan")

        o1 = Order.objects.create(
            code='1AAA', event=event, email='anonymous@🌈.example.org',
            status=Order.STATUS_PENDING, locale='en',
            datetime=now(), expires=now() + timedelta(days=10),
            total=46,
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        op1 = o1.positions.create(
            item=ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={'_scheme': 'given_family', 'given_name': "Alice", 'family_name': "Anonymous"}, positionid=1
        )
        op1.answers.create(question=question, answer="#3b1c4a")
        op1.answers.create(question=question2, answer="vegan").options.set([option2])
        op2 = o1.positions.create(
            item=ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={'_scheme': 'given_family', 'given_name': "Charlie", 'family_name': "de l'Exemple"}, positionid=2
        )
        op2.answers.create(question=question, answer="Red")
        op2.answers.create(question=question2, answer="vegetarian").options.set([option1])

        o2 = Order.objects.create(
            code='2EEE', event=event, email='ephemeral@example.com',
            status=Order.STATUS_PENDING, locale='en',
            datetime=now(), expires=now() + timedelta(days=10),
            total=23,
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        o2.positions.create(
            item=ticket, variation=None,
            price=Decimal("23.00"), attendee_name_parts={'_scheme': 'given_family', 'given_name': "Eve", 'family_name': "Ephemeral"}, positionid=1
        )
        yield event


def expected_order_sync_result():
    return {
        'ticketorders': [
            {
                '_id': 0,
                'ordernumber': 'DUMMY-1AAA',
                'orderemail': 'anonymous@xn--og8h.example.org',
                'status': 'pending',
                'total': '46.00',
                'payment_date': None,
            },
            {
                '_id': 1,
                'ordernumber': 'DUMMY-2EEE',
                'orderemail': 'ephemeral@example.com',
                'status': 'pending',
                'total': '23.00',
                'payment_date': None,
            },
        ],
    }


def expected_sync_result_with_associations():
    return {
        'tickets': [
            {
                '_id': 0,
                'ticketnumber': '1AAA-1',
                'amount': '23.00',
                'firstname': 'Alice',
                'lastname': 'Anonymous',
                'status': 'pending',
                'fav_color': '#3b1c4a',
                'food': 'VEGAN',
                'links': [],
            },
            {
                '_id': 1,
                'ticketnumber': '1AAA-2',
                'amount': '23.00',
                'firstname': 'Charlie',
                'lastname': "de l'Exemple",
                'status': 'pending',
                'fav_color': 'Red',
                'food': 'VEGETARIAN',
                'links': [],
            },
            {
                '_id': 2,
                'ticketnumber': '2EEE-1',
                'amount': '23.00',
                'firstname': 'Eve',
                'lastname': 'Ephemeral',
                'status': 'pending',
                'fav_color': '',
                'food': '',
                'links': [],
            },
        ],
        'ticketorders': [
            {
                '_id': 0,
                'ordernumber': 'DUMMY-1AAA',
                'orderemail': 'anonymous@xn--og8h.example.org',
                'firstname': '',
                'lastname': '',
                'status': 'pending',
                'links': ['link:tickets:0', 'link:tickets:1'],
            },
            {
                '_id': 1,
                'ordernumber': 'DUMMY-2EEE',
                'orderemail': 'ephemeral@example.com',
                'firstname': '',
                'lastname': '',
                'status': 'pending',
                'links': ['link:tickets:2'],
            },
        ],
    }


def _register_with_fake_plugin_name(registry, obj, plugin_name):
    registry.clear()

    class App:
        name = plugin_name

        class PretixPluginMeta:
            pass

    obj.__mocked_app = App
    registry.register(obj)
    registry.registered_entries[obj]['plugin'] = App


class FakeSyncAPI:
    def __init__(self):
        self.fake_database = defaultdict(list)

    def retrieve_object(self, table, search_by_attribute, search_for_value):
        t = self.fake_database[table]
        for idx, record in enumerate(t):
            if record.get(search_by_attribute) == search_for_value:
                return {**record, "_id": idx}
        return None

    def create_or_update_object(self, table, record):
        t = self.fake_database[table]
        if record.get("_id") is not None:
            t[record["_id"]].update(record)
        else:
            record["_id"] = len(t)
            t.append(record)
        return record


class SimpleOrderSync(OutboundSyncProvider):
    identifier = "example1"
    fake_api_client = None

    @property
    def mappings(self):
        return [
            StaticMapping(
                id=1,
                pretix_model='Order', external_object_type='ticketorders',
                pretix_id_field='event_order_code', external_id_field='ordernumber',
                property_mappings=[
                    {
                        "pretix_field": "email",
                        "external_field": "orderemail",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "order_status",
                        "external_field": "status",
                        "value_map": json.dumps({
                            Order.STATUS_PENDING: "pending",
                            Order.STATUS_PAID: "paid",
                            Order.STATUS_EXPIRED: "expired",
                            Order.STATUS_CANCELED: "canceled",
                            Order.STATUS_REFUNDED: "refunded",
                        }),
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "order_total",
                        "external_field": "total",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "payment_date",
                        "external_field": "payment_date",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                ],
            )
        ]

    def sync_object_with_properties(
            self,
            external_id_field,
            id_value,
            properties: list,
            inputs: dict,
            mapping,
            mapped_objects: dict,
            **kwargs,
    ):
        pre_existing_object = self.fake_api_client.retrieve_object(mapping.external_object_type, external_id_field, id_value)
        update_values = assign_properties(properties, pre_existing_object or {}, is_new=pre_existing_object is None, list_sep=";")
        result = self.fake_api_client.create_or_update_object(mapping.external_object_type, {
            **update_values,
            external_id_field: id_value,
            "_id": pre_existing_object and pre_existing_object.get("_id"),
        })

        return {
            "object_type": mapping.external_object_type,
            "external_id_field": external_id_field,
            "id_value": id_value,
            "external_link_href": f"https://external-system.example.com/backend/link/to/{mapping.external_object_type}/123/",
            "external_link_display_name": "Contact #123 - Jane Doe",
            "my_result": result,
        }


@pytest.mark.django_db
def test_simple_order_sync(event):
    _register_with_fake_plugin_name(datasync_providers, SimpleOrderSync, 'testplugin')

    for order in event.orders.order_by("code").all():
        SimpleOrderSync.enqueue_order(order, 'testcase')

    SimpleOrderSync.fake_api_client = FakeSyncAPI()

    sync_all()

    expected = expected_order_sync_result()
    assert SimpleOrderSync.fake_api_client.fake_database == expected

    order_1a = event.orders.get(code='1AAA')
    paydate = now()
    order_1a.payments.create(payment_date=paydate, amount=order_1a.total)
    order_1a.status = Order.STATUS_PAID
    order_1a.save()

    for order in event.orders.order_by("code").all():
        SimpleOrderSync.enqueue_order(order, 'testcase')

    sync_all()

    expected['ticketorders'][0]['status'] = 'paid'
    expected['ticketorders'][0]['payment_date'] = paydate.isoformat()
    assert SimpleOrderSync.fake_api_client.fake_database == expected


@pytest.mark.django_db
def test_enqueue_order_twice(event):
    _register_with_fake_plugin_name(datasync_providers, SimpleOrderSync, 'testplugin')

    for order in event.orders.order_by("code").all():
        SimpleOrderSync.enqueue_order(order, 'testcase_1st')

    for order in event.orders.order_by("code").all():
        SimpleOrderSync.enqueue_order(order, 'testcase_2nd')


class DoNothingSync(SimpleOrderSync):

    def should_sync_order(self, order):
        return False


@pytest.mark.django_db
def test_should_not_sync(event):
    _register_with_fake_plugin_name(datasync_providers, DoNothingSync, 'testplugin')

    DoNothingSync.fake_api_client = FakeSyncAPI()

    for order in event.orders.order_by("code").all():
        DoNothingSync.enqueue_order(order, 'testcase')

    sync_all()

    assert DoNothingSync.fake_api_client.fake_database == {}


StaticMappingWithAssociations = namedtuple('StaticMappingWithAssociations', (
    'id', 'pretix_model', 'external_object_type', 'pretix_id_field', 'external_id_field', 'property_mappings', 'association_mappings'
))
AssociationMapping = namedtuple('AssociationMapping', (
    'via_mapping_id'
))


class OrderAndTicketAssociationSync(OutboundSyncProvider):
    identifier = "example2"
    fake_api_client = None

    @property
    def mappings(self):
        return [
            StaticMappingWithAssociations(
                id=1,
                pretix_model='OrderPosition', external_object_type='tickets',
                pretix_id_field='ticket_id', external_id_field='ticketnumber',
                property_mappings=[
                    {
                        "pretix_field": "ticket_price",
                        "external_field": "amount",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "attendee_name_given_name",
                        "external_field": "firstname",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "attendee_name_family_name",
                        "external_field": "lastname",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "order_status",
                        "external_field": "status",
                        "value_map": json.dumps({
                            Order.STATUS_PENDING: "pending",
                            Order.STATUS_PAID: "paid",
                            Order.STATUS_EXPIRED: "expired",
                            Order.STATUS_CANCELED: "canceled",
                            Order.STATUS_REFUNDED: "refunded",
                        }),
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "question_FAV_COLOR",
                        "external_field": "fav_color",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "question_FOOD_PREF",
                        "external_field": "food",
                        "value_map": json.dumps({
                            "F1": "VEGETARIAN",
                            "F2": "VEGAN",
                        }),
                        "overwrite": MODE_OVERWRITE,
                    },
                ],
                association_mappings=[],
            ),
            StaticMappingWithAssociations(
                id=2,
                pretix_model='Order', external_object_type='ticketorders',
                pretix_id_field='event_order_code', external_id_field='ordernumber',
                property_mappings=[
                    {
                        "pretix_field": "email",
                        "external_field": "orderemail",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "invoice_address_name_given_name",
                        "external_field": "firstname",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "invoice_address_name_family_name",
                        "external_field": "lastname",
                        "value_map": "",
                        "overwrite": MODE_OVERWRITE,
                    },
                    {
                        "pretix_field": "order_status",
                        "external_field": "status",
                        "value_map": json.dumps({
                            Order.STATUS_PENDING: "pending",
                            Order.STATUS_PAID: "paid",
                            Order.STATUS_EXPIRED: "expired",
                            Order.STATUS_CANCELED: "canceled",
                            Order.STATUS_REFUNDED: "refunded",
                        }),
                        "overwrite": MODE_OVERWRITE,
                    },
                ],
                association_mappings=[
                    AssociationMapping(via_mapping_id=1)
                ],
            ),
        ]

    def sync_object_with_properties(
            self,
            external_id_field,
            id_value,
            properties: list,
            inputs: dict,
            mapping,
            mapped_objects: dict,
            **kwargs,
    ):
        pre_existing_object = self.fake_api_client.retrieve_object(mapping.external_object_type, external_id_field, id_value)
        update_values = assign_properties(properties, pre_existing_object or {}, is_new=pre_existing_object is None, list_sep=";")
        result = self.fake_api_client.create_or_update_object(mapping.external_object_type, {
            **update_values,
            external_id_field: id_value,
            "_id": pre_existing_object and pre_existing_object.get("_id"),
            "links": [
                f"link:{obj.external_object_type}:{obj.sync_info['my_result']['_id']}"
                for am in mapping.association_mappings
                for obj in mapped_objects[am.via_mapping_id]
            ]
        })

        return {
            "object_type": mapping.external_object_type,
            "external_id_field": external_id_field,
            "id_value": id_value,
            "external_link_href": f"https://external-system.example.com/backend/link/to/{mapping.external_object_type}/123/",
            "external_link_display_name": "Contact #123 - Jane Doe",
            "my_result": result,
        }


@pytest.mark.django_db
def test_association_sync(event):
    _register_with_fake_plugin_name(datasync_providers, OrderAndTicketAssociationSync, 'testplugin')

    for order in event.orders.order_by("code").all():
        OrderAndTicketAssociationSync.enqueue_order(order, 'testcase')

    OrderAndTicketAssociationSync.fake_api_client = FakeSyncAPI()

    sync_all()

    expected = expected_sync_result_with_associations()
    assert OrderAndTicketAssociationSync.fake_api_client.fake_database == expected

    order_1a = event.orders.get(code='1AAA')
    order_1a.status = Order.STATUS_PAID
    order_1a.save()

    for order in event.orders.order_by("code").all():
        OrderAndTicketAssociationSync.enqueue_order(order, 'testcase')

    sync_all()

    expected['tickets'][0]['status'] = 'paid'
    expected['tickets'][1]['status'] = 'paid'
    expected['ticketorders'][0]['status'] = 'paid'
    assert OrderAndTicketAssociationSync.fake_api_client.fake_database == expected


@pytest.mark.django_db
def test_legacy_name_splitting(event):
    _register_with_fake_plugin_name(datasync_providers, OrderAndTicketAssociationSync, 'testplugin')

    for order in event.orders.order_by("code").all():
        OrderAndTicketAssociationSync.enqueue_order(order, 'testcase')
    InvoiceAddress.objects.create(order=order, name_parts={'_scheme': 'full', 'full_name': 'A B C D'})
    order.refresh_from_db()
    print(order.invoice_address.name_parts)
    print(order.invoice_address.name)

    event.settings.name_scheme = 'full'

    OrderAndTicketAssociationSync.fake_api_client = FakeSyncAPI()

    sync_all()

    expected = expected_sync_result_with_associations()
    expected['tickets'][1]['firstname'] = "Charlie de"  # yes, this splits incorrectly, hence it's legacy
    expected['tickets'][1]['lastname'] = "l'Exemple"
    expected['ticketorders'][1]['firstname'] = "A B C"
    expected['ticketorders'][1]['lastname'] = "D"
    assert OrderAndTicketAssociationSync.fake_api_client.fake_database == expected


def test_assign_properties():
    assert assign_properties(
        [("name", "Alice", MODE_OVERWRITE)], {"name": "A"}, is_new=False, list_sep=";"
    ) == {"name": "Alice"}
    assert (
        assign_properties([("name", "Alice", MODE_SET_IF_NEW)], {}, is_new=False, list_sep=";") == {}
    )
    assert assign_properties([("name", "Alice", MODE_SET_IF_NEW)], {}, is_new=True, list_sep=";") == {
        "name": "Alice"
    }
    assert assign_properties(
        [
            ("name", "Alice", MODE_SET_IF_NEW),
            ("name", "A", MODE_SET_IF_NEW),
        ],
        {},
        is_new=True,
        list_sep=";",
    ) == {"name": "Alice"}
    assert (
        assign_properties(
            [
                ("name", "Alice", MODE_SET_IF_NEW),
                ("name", "A", MODE_SET_IF_NEW),
            ],
            {"name": "Bob"},
            is_new=False,
            list_sep=";",
        )
        == {}
    )
    assert (
        assign_properties(
            [
                ("name", "Alice", MODE_SET_IF_NEW),
                ("name", "A", MODE_SET_IF_NEW),
            ],
            {},
            is_new=False,
            list_sep=";",
        )
        == {}
    )
    assert assign_properties(
        [
            ("name", "Alice", MODE_SET_IF_EMPTY),
            ("name", "A", MODE_SET_IF_EMPTY),
        ],
        {},
        is_new=True,
        list_sep=";",
    ) == {"name": "Alice"}
    assert (
        assign_properties(
            [
                ("name", "Alice", MODE_SET_IF_EMPTY),
                ("name", "A", MODE_SET_IF_EMPTY),
            ],
            {"name": "Bob"},
            is_new=False,
            list_sep=";",
        )
        == {}
    )
    assert assign_properties(
        [("name", "Alice", MODE_SET_IF_EMPTY)], {}, is_new=False, list_sep=";"
    ) == {"name": "Alice"}

    assert assign_properties(
        [("name", "Alice", MODE_SET_IF_EMPTY)], {}, is_new=False, list_sep=";"
    ) == {"name": "Alice"}

    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {}, is_new=False, list_sep=";"
    ) == {"colors": "red"}
    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {"colors": "red"}, is_new=False, list_sep=";"
    ) == {}
    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {"colors": "blue"}, is_new=False, list_sep=";"
    ) == {"colors": "blue;red"}
    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {"colors": "green;blue"}, is_new=False, list_sep=";"
    ) == {"colors": "green;blue;red"}
    assert assign_properties(
        [("colors", "red", MODE_APPEND_LIST)], {"colors": ["green", "blue"]}, is_new=False, list_sep=None
    ) == {"colors": ["green", "blue", "red"]}
    assert assign_properties(
        [("colors", "green", MODE_APPEND_LIST)], {"colors": ["green", "blue"]}, is_new=False, list_sep=None
    ) == {}
