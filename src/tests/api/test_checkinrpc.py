#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
import datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_countries.fields import Country
from django_scopes import scopes_disabled
from i18nfield.strings import LazyI18nString
from tests.const import SAMPLE_PNG

from pretix.api.serializers.item import QuestionSerializer
from pretix.base.models import (
    Checkin, InvoiceAddress, Order, OrderPosition, ReusableMedium,
)

# Lots of this code is overlapping with test_checkin.py, and some of it is arguably redundant since it's triggering
# the same backend code paths (for now). However, this is SUCH a critical part of pretix that we don't want to take
# the risk of some day having differing implementations and missing vital test coverage.


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item_on_event2(event2):
    return event2.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def other_item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def order(event, item, other_item, taxrule):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='FOO', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PAID, secret="k24fiuwvu8kxz3y1",
            datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
            expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=datetime.timezone.utc),
            total=46, locale='en'
        )
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        op1 = OrderPosition.objects.create(
            order=o,
            positionid=1,
            item=item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Peter"},
            secret="z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
            pseudonymization_id="ABCDEFGHKL",
        )
        OrderPosition.objects.create(
            order=o,
            positionid=2,
            item=other_item,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Michael"},
            secret="sf4HZG73fU6kwddgjg2QOusFbYZwVKpK",
            pseudonymization_id="BACDEFGHKL",
        )
        OrderPosition.objects.create(
            order=o,
            positionid=3,
            item=other_item,
            addon_to=op1,
            variation=None,
            price=Decimal("0"),
            secret="3u4ez6vrrbgb3wvezxhq446p548dt2wn",
            pseudonymization_id="FOOBAR12345",
        )
        return o


@pytest.fixture
def order2(event2, item_on_event2):
    testtime = datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        o = Order.objects.create(
            code='BAR', event=event2, email='dummy@dummy.test',
            status=Order.STATUS_PAID, secret="ylptCPNOxTyA",
            datetime=datetime.datetime(2017, 12, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
            expires=datetime.datetime(2017, 12, 10, 10, 0, 0, tzinfo=datetime.timezone.utc),
            total=46, locale='en'
        )
        InvoiceAddress.objects.create(order=o, company="Sample company", country=Country('NZ'))
        OrderPosition.objects.create(
            order=o,
            positionid=1,
            item=item_on_event2,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "John"},
            secret="y8tPmyc5BEK2G9pifSNumwp4NXAaIE4P",
            pseudonymization_id="A23456789",
        )
        OrderPosition.objects.create(
            order=o,
            positionid=2,
            item=item_on_event2,
            variation=None,
            price=Decimal("23"),
            attendee_name_parts={'full_name': "Paul"},
            secret="xrahgLCfodoNOIZ4uxn75gNBM1bb6m1h",
            pseudonymization_id="B23456797345",
        )
        return o


TEST_ORDERPOSITION1_RES = {
    "id": 1,
    "require_attention": False,
    "order__status": "p",
    "order": "FOO",
    "positionid": 1,
    "item": 1,
    "variation": None,
    "price": "23.00",
    "attendee_name": "Peter",
    "attendee_name_parts": {'full_name': "Peter"},
    "attendee_email": None,
    "voucher": None,
    "tax_rate": "0.00",
    "tax_value": "0.00",
    "tax_rule": None,
    "secret": "z3fsn8jyufm5kpk768q69gkbyr5f4h6w",
    "addon_to": None,
    "checkins": [],
    "downloads": [],
    "answers": [],
    "seat": None,
    "company": None,
    "street": None,
    "zipcode": None,
    "city": None,
    "country": None,
    "state": None,
    "subevent": None,
    "valid_from": None,
    "valid_until": None,
    "blocked": None,
    "pseudonymization_id": "ABCDEFGHKL",
}


@pytest.fixture
def clist(event, item):
    c = event.checkin_lists.create(name="Default", all_products=False)
    c.limit_products.add(item)
    return c


@pytest.fixture
def clist_all(event, item):
    c = event.checkin_lists.create(name="Default", all_products=True)
    return c


@pytest.fixture
def clist_event2(event2):
    c = event2.checkin_lists.create(name="Event 2", all_products=True)
    return c


def _redeem(token_client, org, clist, p, body=None, query=''):
    body = body or {}
    if isinstance(clist, list):
        body['lists'] = [c.pk for c in clist]
    else:
        body['lists'] = [clist.pk]
    body['secret'] = p
    return token_client.post('/api/v1/organizers/{}/checkinrpc/redeem/{}'.format(
        org.slug, query,
    ), body, format='json')


@pytest.mark.django_db
def test_query_load(token_client, organizer, clist, event, order, django_assert_max_num_queries):
    with scopes_disabled():
        p = order.positions.first()
    with django_assert_max_num_queries(30):
        resp = _redeem(token_client, organizer, clist, p.secret)
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_custom_datetime(token_client, organizer, clist, event, order):
    dt = now() - datetime.timedelta(days=1)
    dt = dt.replace(microsecond=0)
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {
        'datetime': dt.isoformat()
    })
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        assert Checkin.objects.last().datetime == dt


@pytest.mark.django_db
def test_name_fallback(token_client, organizer, clist, event, order):
    order.invoice_address.name_parts = {'_legacy': 'Paul'}
    order.invoice_address.save()
    with scopes_disabled():
        op = order.positions.first()
    op.attendee_name_cached = None
    op.attendee_name_parts = {}
    op.save()
    resp = _redeem(token_client, organizer, clist, op.secret, {})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    assert resp.data['position']['attendee_name'] == 'Paul'
    assert resp.data['position']['attendee_name_parts'] == {'_legacy': 'Paul'}


@pytest.mark.django_db
def test_by_pk_not_allowed(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.pk, {})
    assert resp.status_code == 404


@pytest.mark.django_db
def test_by_secret(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_by_secret_special_chars(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    p.secret = "abc+-/=="
    p.save()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_by_medium(token_client, organizer, clist, event, order):
    with scopes_disabled():
        ReusableMedium.objects.create(
            type="barcode",
            identifier="abcdef",
            organizer=organizer,
            linked_orderposition=order.positions.first(),
        )
    resp = _redeem(token_client, organizer, clist, "abcdef", {"source_type": "barcode"})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        ci = clist.checkins.get(position=order.positions.first())
    assert ci.raw_barcode == "abcdef"
    assert ci.raw_source_type == "barcode"


@pytest.mark.django_db
def test_by_medium_not_connected(token_client, organizer, clist, event, order):
    with scopes_disabled():
        ReusableMedium.objects.create(
            type="barcode",
            identifier="abcdef",
            organizer=organizer,
        )
    resp = _redeem(token_client, organizer, clist, "abcdef", {"source_type": "barcode"})
    assert resp.status_code == 404
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'invalid'


@pytest.mark.django_db
def test_by_medium_wrong_type(token_client, organizer, clist, event, order):
    with scopes_disabled():
        ReusableMedium.objects.create(
            type="nfc_uid",
            identifier="abcdef",
            organizer=organizer,
            linked_orderposition=order.positions.first(),
        )
    resp = _redeem(token_client, organizer, clist, "abcdef", {"source_type": "barcode"})
    assert resp.status_code == 404
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'invalid'
    resp = _redeem(token_client, organizer, clist, "abcdef", {"source_type": "nfc_uid"})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_by_medium_inactive(token_client, organizer, clist, event, order):
    with scopes_disabled():
        ReusableMedium.objects.create(
            type="barcode",
            identifier="abcdef",
            organizer=organizer,
            active=False,
            linked_orderposition=order.positions.first(),
        )
    resp = _redeem(token_client, organizer, clist, "abcdef", {"source_type": "barcode"})
    assert resp.status_code == 404
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'invalid'


@pytest.mark.django_db
def test_only_once(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'already_redeemed'


@pytest.mark.django_db
def test_reupload_same_nonce(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {'nonce': 'foobar'})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    resp = _redeem(token_client, organizer, clist, p.secret, {'nonce': 'foobar'})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_allow_multiple(token_client, organizer, clist, event, order):
    clist.allow_multiple_entries = True
    clist.save()
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        assert p.checkins.count() == 2


@pytest.mark.django_db
def test_allow_multiple_reupload_same_nonce(token_client, organizer, clist, event, order):
    clist.allow_multiple_entries = True
    clist.save()
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {'nonce': 'foobar'})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    resp = _redeem(token_client, organizer, clist, p.secret, {'nonce': 'foobar'})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        assert p.checkins.count() == 1


@pytest.mark.django_db
def test_multiple_different_list(token_client, organizer, clist, clist_all, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {'nonce': 'foobar'})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    resp = _redeem(token_client, organizer, clist_all, p.secret, {'nonce': 'baz'})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_forced_multiple(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    resp = _redeem(token_client, organizer, clist, p.secret, {'force': True})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_forced_canceled(token_client, organizer, clist, event, order):
    order.status = Order.STATUS_CANCELED
    order.save()
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'error'
    resp = _redeem(token_client, organizer, clist, p.secret, {'force': True})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        ci = p.checkins.get()
        assert ci.force_sent
        assert ci.forced


@pytest.mark.django_db
def test_forced_flag_set_if_required(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {'force': True})
    with scopes_disabled():
        assert not p.checkins.order_by('pk').last().forced
        assert p.checkins.order_by('pk').last().force_sent
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    resp = _redeem(token_client, organizer, clist, p.secret, {'force': True})
    with scopes_disabled():
        assert p.checkins.order_by('pk').last().forced
        assert p.checkins.order_by('pk').last().force_sent
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_require_product(token_client, organizer, clist, event, order):
    with scopes_disabled():
        clist.limit_products.clear()
        p = order.positions.first()

    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'product'


@pytest.mark.django_db
def test_require_paid(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()

    order.status = Order.STATUS_CANCELED
    order.save()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'canceled'

    order.status = Order.STATUS_PENDING
    order.save()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'unpaid'

    resp = _redeem(token_client, organizer, clist, p.secret, {'ignore_unpaid': True})
    assert resp.status_code == 400
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'unpaid'

    clist.include_pending = True
    clist.save()

    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'error'
    assert resp.data['reason'] == 'unpaid'

    resp = _redeem(token_client, organizer, clist, p.secret, {'ignore_unpaid': True})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.fixture
def question(event, item):
    q = event.questions.create(question=LazyI18nString('Size'), type='C', required=True, ask_during_checkin=True)
    a1 = q.options.create(answer=LazyI18nString("M"))
    a2 = q.options.create(answer=LazyI18nString("L"))
    q.items.add(item)
    return q, a1, a2


@pytest.mark.django_db
def test_question_number(token_client, organizer, clist, event, order, question):
    with scopes_disabled():
        p = order.positions.first()
        question[0].options.all().delete()
    question[0].type = 'N'
    question[0].save()

    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]

    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {question[0].pk: "3.24"}})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        assert order.positions.first().answers.get(question=question[0]).answer == '3.24'


@pytest.mark.django_db
def test_question_choice(token_client, organizer, clist, event, order, question):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]

    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {question[0].pk: str(question[1].pk)}})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        assert order.positions.first().answers.get(question=question[0]).answer == 'M'
        assert list(order.positions.first().answers.get(question=question[0]).options.all()) == [question[1]]


@pytest.mark.django_db
def test_question_choice_identifier(token_client, organizer, clist, event, order, question):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]

    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {question[0].pk: str(question[1].identifier)}})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        assert order.positions.first().answers.get(question=question[0]).answer == 'M'
        assert list(order.positions.first().answers.get(question=question[0]).options.all()) == [question[1]]


@pytest.mark.django_db
def test_question_invalid(token_client, organizer, clist, event, order, question):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {question[0].pk: "A"}})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]


@pytest.mark.django_db
def test_question_required(token_client, organizer, clist, event, order, question):
    with scopes_disabled():
        p = order.positions.first()
    question[0].required = True
    question[0].save()

    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]

    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {question[0].pk: ""}})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]


@pytest.mark.django_db
def test_question_optional(token_client, organizer, clist, event, order, question):
    with scopes_disabled():
        p = order.positions.first()
    question[0].required = False
    question[0].save()

    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {}})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]

    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {question[0].pk: ""}})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'


@pytest.mark.django_db
def test_question_multiple_choice(token_client, organizer, clist, event, order, question):
    with scopes_disabled():
        p = order.positions.first()
    question[0].type = 'M'
    question[0].save()

    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]

    resp = _redeem(token_client, organizer, clist, p.secret,
                   {'answers': {question[0].pk: "{},{}".format(question[1].pk, question[2].pk)}})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        assert order.positions.first().answers.get(question=question[0]).answer == 'M, L'
        assert set(order.positions.first().answers.get(question=question[0]).options.all()) == {question[1],
                                                                                                question[2]}


@pytest.mark.django_db
def test_question_upload(token_client, organizer, clist, event, order, question):
    r = token_client.post(
        '/api/v1/upload',
        data={
            'media_type': 'image/png',
            'file': ContentFile(SAMPLE_PNG)
        },
        format='upload',
        HTTP_CONTENT_DISPOSITION='attachment; filename="file.png"',
    )
    assert r.status_code == 201
    file_id_png = r.data['id']

    with scopes_disabled():
        p = order.positions.first()
    question[0].type = 'F'
    question[0].save()

    resp = _redeem(token_client, organizer, clist, p.secret, {})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'
    with scopes_disabled():
        assert resp.data['questions'] == [QuestionSerializer(question[0]).data]

    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {question[0].pk: "invalid"}})
    assert resp.status_code == 400
    assert resp.data['status'] == 'incomplete'

    resp = _redeem(token_client, organizer, clist, p.secret, {'answers': {question[0].pk: file_id_png}})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    with scopes_disabled():
        assert order.positions.first().answers.get(question=question[0]).answer.startswith('file://')
        assert order.positions.first().answers.get(question=question[0]).file


@pytest.mark.django_db
def test_store_failed(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = token_client.post('/api/v1/organizers/{}/events/{}/checkinlists/{}/failed_checkins/'.format(
        organizer.slug, event.slug, clist.pk,
    ), {
        'raw_barcode': '123456',
        'error_reason': 'invalid'
    }, format='json')
    assert resp.status_code == 201
    with scopes_disabled():
        assert Checkin.all.filter(successful=False).exists()

    resp = token_client.post('/api/v1/organizers/{}/events/{}/checkinlists/{}/failed_checkins/'.format(
        organizer.slug, event.slug, clist.pk,
    ), {
        'raw_barcode': '123456',
        'position': p.pk,
        'error_reason': 'unpaid'
    }, format='json')
    assert resp.status_code == 201
    with scopes_disabled():
        assert p.all_checkins.filter(successful=False).count() == 1

    resp = token_client.post('/api/v1/organizers/{}/events/{}/checkinlists/{}/failed_checkins/'.format(
        organizer.slug, event.slug, clist.pk,
    ), {
        'position': p.pk,
        'error_reason': 'unpaid'
    }, format='json')
    assert resp.status_code == 400

    resp = token_client.post('/api/v1/organizers/{}/events/{}/checkinlists/{}/failed_checkins/'.format(
        organizer.slug, event.slug, clist.pk,
    ), {
        'raw_barcode': '123456',
        'error_reason': 'unknown'
    }, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_redeem_unknown(token_client, organizer, clist, event, order):
    resp = _redeem(token_client, organizer, clist, 'unknown_secret', {'force': True})
    assert resp.status_code == 404
    assert resp.data["status"] == "error"
    assert resp.data["reason"] == "invalid"
    with scopes_disabled():
        assert not Checkin.objects.last()


@pytest.mark.django_db
def test_redeem_unknown_revoked(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
        event.revoked_secrets.create(position=p, secret='revoked_secret')
    resp = _redeem(token_client, organizer, clist, 'revoked_secret', {})
    assert resp.status_code == 400
    assert resp.data["status"] == "error"
    assert resp.data["reason"] == "revoked"
    with scopes_disabled():
        assert not Checkin.objects.last()


@pytest.mark.django_db
def test_redeem_unknown_revoked_force(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
        event.revoked_secrets.create(position=p, secret='revoked_secret')
    resp = _redeem(token_client, organizer, clist, 'revoked_secret', {'force': True})
    assert resp.status_code == 201
    assert resp.data["status"] == "ok"
    with scopes_disabled():
        ci = Checkin.objects.last()
        assert ci.forced
        assert ci.force_sent
        assert ci.position == p


@pytest.mark.django_db
def test_redeem_addon_if_match_disabled(token_client, organizer, clist, other_item, event, order):
    with scopes_disabled():
        clist.all_products = False
        clist.save()
        clist.limit_products.set([other_item])
    resp = _redeem(token_client, organizer, clist, 'z3fsn8jyufm5kpk768q69gkbyr5f4h6w', {})
    assert resp.status_code == 400
    assert resp.data["status"] == "error"
    assert resp.data["reason"] == "product"
    with scopes_disabled():
        assert not Checkin.objects.last()


@pytest.mark.django_db
def test_redeem_addon_if_match_enabled(token_client, organizer, clist, other_item, event, order):
    with scopes_disabled():
        clist.all_products = False
        clist.addon_match = True
        clist.save()
        clist.limit_products.set([other_item])
        p = order.positions.first().addons.all().first()
    resp = _redeem(token_client, organizer, clist, 'z3fsn8jyufm5kpk768q69gkbyr5f4h6w', {})
    assert resp.status_code == 201
    assert resp.data['status'] == 'ok'
    assert resp.data['position']['attendee_name'] == 'Peter'  # test propagation of names
    assert resp.data['position']['item'] == other_item.pk
    with scopes_disabled():
        ci = Checkin.objects.last()
        assert ci.position == p


@pytest.mark.django_db
def test_redeem_addon_if_match_ambiguous(token_client, organizer, clist, item, other_item, event, order):
    with scopes_disabled():
        clist.all_products = False
        clist.addon_match = True
        clist.save()
        clist.limit_products.set([item, other_item])
    resp = _redeem(token_client, organizer, clist, 'z3fsn8jyufm5kpk768q69gkbyr5f4h6w', {})
    assert resp.status_code == 400
    assert resp.data["status"] == "error"
    assert resp.data["reason"] == "ambiguous"
    with scopes_disabled():
        assert not Checkin.objects.last()


@pytest.mark.django_db
def test_redeem_addon_if_match_and_revoked_force(token_client, organizer, clist, other_item, event, order):
    with scopes_disabled():
        event.revoked_secrets.create(position=order.positions.get(positionid=1), secret='revoked_secret')
        clist.all_products = False
        clist.addon_match = True
        clist.save()
        clist.limit_products.set([other_item])
        p = order.positions.first().addons.all().first()
    resp = _redeem(token_client, organizer, clist, 'revoked_secret', {'force': True})
    assert resp.status_code == 201
    assert resp.data["status"] == "ok"
    with scopes_disabled():
        ci = Checkin.objects.last()
        assert ci.forced
        assert ci.force_sent
        assert ci.position == p


@pytest.mark.django_db
def test_redeem_multi_list(token_client, organizer, clist, clist_event2, order, order2):
    with scopes_disabled():
        p = order.positions.first()
        p2 = order2.positions.first()
    resp = _redeem(token_client, organizer, [clist, clist_event2], p.secret)
    assert resp.status_code == 201
    assert resp.data['position']['id'] == p.pk
    assert resp.data['list'] == {'id': clist.pk, 'name': 'Default', 'event': 'dummy', 'subevent': None, 'include_pending': False}
    resp = _redeem(token_client, organizer, [clist, clist_event2], p2.secret)
    assert resp.status_code == 201
    assert resp.data['position']['id'] == p2.pk
    assert resp.data['list'] == {'id': clist_event2.pk, 'name': 'Event 2', 'event': 'dummy2', 'subevent': None, 'include_pending': False}
    resp = _redeem(token_client, organizer, [clist], p2.secret)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_redeem_no_list(token_client, organizer, clist, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, [], p.secret)
    assert resp.status_code == 400
    assert resp.data == ['No check-in list passed.']


@pytest.mark.django_db
def test_redeem_conflicting_lists(token_client, organizer, clist, clist_all, event, order):
    with scopes_disabled():
        p = order.positions.first()
    resp = _redeem(token_client, organizer, [clist_all, clist], p.secret)
    assert resp.status_code == 400
    assert resp.data == ['Selecting two check-in lists from the same event is unsupported.']


@pytest.mark.django_db
def test_search(token_client, organizer, event, clist, clist_all, item, other_item, order,
                django_assert_max_num_queries):
    with scopes_disabled():
        p1 = dict(TEST_ORDERPOSITION1_RES)
        p1["id"] = order.positions.get(positionid=1).pk
        p1["item"] = item.pk

    with django_assert_max_num_queries(17):
        resp = token_client.get(
            '/api/v1/organizers/{}/checkinrpc/search/?list={}&search=z3fsn8jyu'.format(organizer.slug, clist_all.pk))
    assert resp.status_code == 200
    assert [p1] == resp.data['results']


@pytest.mark.django_db
def test_search_no_list(token_client, organizer, event, clist, clist_all, item, other_item, order):
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?search=z3fsn8jyu'.format(organizer.slug))
    assert resp.status_code == 400
    assert resp.data == ['No check-in list passed.']


@pytest.mark.django_db
def test_search_conflicting_lists(token_client, organizer, event, clist, clist_all, item, other_item, order):
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?search=z3fsn8jyu&list={}&list={}'.format(organizer.slug, clist.pk, clist_all.pk))
    assert resp.status_code == 400
    assert resp.data == ['Selecting two check-in lists from the same event is unsupported.']


@pytest.mark.django_db
def test_search_multiple_lists(token_client, organizer, clist_all, clist_event2, order2, order):
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?list={}&list={}&search=dummy.test&ordering=attendee_name'.format(
            organizer.slug, clist_all.pk, clist_event2.pk
        )
    )
    assert resp.status_code == 200
    with scopes_disabled():
        assert resp.data['results'][0]['id'] == order2.positions.get(positionid=1).pk
        assert resp.data['results'][1]['id'] == order.positions.get(positionid=2).pk


@pytest.mark.django_db
def test_without_permission(token_client, event, team, organizer, clist_all, order):
    with scopes_disabled():
        team.can_view_orders = False
        team.can_change_orders = False
        team.can_checkin_orders = False
        team.save()
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?list={}&search=dummy.test&ordering=attendee_name'.format(organizer.slug, clist_all.pk))
    assert resp.status_code == 403
    assert resp.data == {
        "detail": f"You requested lists that do not exist or that you do not have access to: {clist_all.pk}"
    }

    resp = _redeem(token_client, organizer, [clist_all], "foobar")
    assert resp.status_code == 400
    assert resp.data == {
        "lists": [f'Invalid pk "{clist_all.pk}" - object does not exist.']
    }


@pytest.mark.django_db
def test_without_permission_for_one_list(token_client, event, team, organizer, clist_all, clist_event2, order2, order):
    with scopes_disabled():
        team.all_events = False
        team.save()
        team.limit_events.set([event])
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?list={}&list={}&search=dummy.test&ordering=attendee_name'.format(
            organizer.slug, clist_all.pk, clist_event2.pk
        )
    )
    assert resp.status_code == 403
    assert resp.data == {
        "detail": f"You requested lists that do not exist or that you do not have access to: {clist_event2.pk}"
    }

    resp = _redeem(token_client, organizer, [clist_all, clist_event2], "foobar")
    assert resp.status_code == 400
    assert resp.data == {
        "lists": [f'Invalid pk "{clist_event2.pk}" - object does not exist.']
    }


@pytest.mark.django_db
def test_checkin_only_permission(token_client, event, team, organizer, clist_all, order):
    with scopes_disabled():
        p = order.positions.first()
    clist_all.allow_multiple_entries = True
    clist_all.save()

    # With all permissions, I can submit very short search terms
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?list={}&search=du&ordering=attendee_name'.format(organizer.slug, clist_all.pk))
    assert resp.data['count'] > 0

    # With all permissions, I can request PDF data during checkin
    resp = _redeem(token_client, organizer, [clist_all], p.secret, {}, '?pdf_data=true')
    assert resp.status_code == 201
    assert resp.data['position'].get('pdf_data')

    with scopes_disabled():
        team.can_view_orders = False
        team.can_change_orders = False
        team.can_checkin_orders = True
        team.save()

    # With limited permissions, I can not search with a 2-character query
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?list={}&search=du&ordering=attendee_name'.format(organizer.slug, clist_all.pk))
    assert resp.status_code == 200
    assert resp.data['count'] == 0

    # With limited permissions, I can search with a 4-character query
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?list={}&search=dummy&ordering=attendee_name'.format(organizer.slug, clist_all.pk))
    assert resp.status_code == 200
    assert resp.data['count'] > 0

    # With limited permissions, I can not request PDF data during checkin
    resp = _redeem(token_client, organizer, [clist_all], p.secret, {}, '?pdf_data=true')
    assert resp.status_code == 201
    assert not resp.data['position'].get('pdf_data')


@pytest.mark.django_db
def test_checkin_no_pdf_data(token_client, event, team, organizer, clist_all, order):
    resp = token_client.get(
        '/api/v1/organizers/{}/checkinrpc/search/?list={}&search=dummy&pdf_data=true'.format(organizer.slug, clist_all.pk))
    assert not resp.data['results'][0].get('pdf_data')
