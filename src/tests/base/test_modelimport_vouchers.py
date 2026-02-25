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
import csv
from decimal import Decimal
from io import StringIO

import pytest
from django.core.files.base import ContentFile
from django.utils.timezone import now
from django_scopes import scopes_disabled
from unittest import mock

from pretix.base.models import CachedFile, Event, Item, Organizer, User
from pretix.base.services.modelimport import DataImportError, import_vouchers


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(), plugins='pretix.plugins.banktransfer,pretix.plugins.paypal'
    )
    return event


@pytest.fixture
def item(event):
    return Item.objects.create(event=event, name="Ticket", default_price=23)


@pytest.fixture
def user():
    return User.objects.create_user('test@localhost', 'test')


def inputfile_factory(multiplier=1):
    d = [
        {
            'A': 'ABCDE123',
            'B': 'Ticket',
            'C': 'True',
            'D': '2021-06-28 11:00:00',
            'E': '2',
            'F': '1',
        },
        {
            'A': 'GHIJK432',
            'B': 'Ticket',
            'C': 'False',
            'D': '2021-05-28 11:00:00',
            'E': '2',
            'F': '1',
        },
    ]
    if multiplier > 1:
        d = d * multiplier
    f = StringIO()
    w = csv.DictWriter(f, ['A', 'B', 'C', 'D', 'E', 'F'], dialect=csv.excel)
    w.writeheader()
    w.writerows(d)
    f.seek(0)
    c = CachedFile.objects.create(type="text/csv", filename="input.csv")
    c.file.save("input.csv", ContentFile(f.read()))
    return c


def inputfile_with_recipients():
    d = [
        {
            'A': 'ABCDE123',
            'B': 'Ticket',
            'C': 'True',
            'D': '2021-06-28 11:00:00',
            'E': '2',
            'F': '1',
            'G': 'alice@example.org',
            'H': 'Alice',
        },
        {
            'A': 'GHIJK432',
            'B': 'Ticket',
            'C': 'False',
            'D': '2021-05-28 11:00:00',
            'E': '2',
            'F': '1',
            'G': 'bob@example.org',
            'H': 'Bob',
        },
    ]
    f = StringIO()
    w = csv.DictWriter(f, ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'], dialect=csv.excel)
    w.writeheader()
    w.writerows(d)
    f.seek(0)
    c = CachedFile.objects.create(type="text/csv", filename="input.csv")
    c.file.save("input.csv", ContentFile(f.read()))
    return c


def inputfile_with_invalid_email():
    d = [
        {
            'A': 'ABCDE123',
            'B': 'Ticket',
            'C': 'True',
            'D': '2021-06-28 11:00:00',
            'E': '2',
            'F': '1',
            'G': 'not-an-email',
            'H': 'Alice',
        },
    ]
    f = StringIO()
    w = csv.DictWriter(f, ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'], dialect=csv.excel)
    w.writeheader()
    w.writerows(d)
    f.seek(0)
    c = CachedFile.objects.create(type="text/csv", filename="input.csv")
    c.file.save("input.csv", ContentFile(f.read()))
    return c


DEFAULT_SETTINGS = {
    'code': 'csv:A',
    'max_usages': 'static:1',
    'min_usages': 'static:1',
    'budget': 'empty',
    'valid_until': 'csv:D',
    'block_quota': 'static:false',
    'allow_ignore_quota': 'static:false',
    'price_mode': 'static:none',
    'value': 'empty',
    'item': 'csv:B',
    'variation': 'empty',
    'quota': 'empty',
    'seat': 'empty',
    'tag': 'empty',
    'comment': 'empty',
    'send': False,
    'show_hidden_items': 'static:true',
    'all_addons_included': 'csv:C',
    'all_bundles_included': 'static:false',
}


@pytest.mark.django_db
@scopes_disabled()
def test_import_simple(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    import_vouchers.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert event.vouchers.count() == 2
    v = event.vouchers.get(code="ABCDE123")
    assert v.item == item
    assert v.all_addons_included
    assert not v.all_bundles_included
    assert v.valid_until.year == 2021


@pytest.mark.django_db
@scopes_disabled()
def test_import_code_unique(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    import_vouchers.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    )
    assert event.vouchers.count() == 2

    with pytest.raises(DataImportError) as excinfo:
        import_vouchers.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert ('Error while importing value "ABCDE123" for column "Voucher code" in line "1": '
            'A voucher with this code already exists.') in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_integer_invalid(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    settings['min_usages'] = 'csv:A'
    with pytest.raises(DataImportError) as excinfo:
        import_vouchers.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'column "Minimum usages" in line "1": Enter a valid integer.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_model_validation(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    settings['min_usages'] = 'csv:E'
    with pytest.raises(DataImportError) as excinfo:
        import_vouchers.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'The maximum number of usages may not be lower than the minimum number of usages.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_price_mode_validation(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    settings['value'] = 'csv:F'
    with pytest.raises(DataImportError) as excinfo:
        import_vouchers.apply(
            args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
        ).get()
    assert 'It is pointless to set a value without a price mode.' in str(excinfo.value)

    settings['price_mode'] = 'static:percent'
    import_vouchers.apply(
        args=(event.pk, inputfile_factory().id, settings, 'en', user.pk)
    ).get()
    assert event.vouchers.count() == 2
    v = event.vouchers.get(code="ABCDE123")
    assert v.price_mode == "percent"
    assert v.value == Decimal("1.00")


@pytest.mark.django_db
@scopes_disabled()
def test_import_send_requires_email_column(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    settings.update({
        'send': True,
        'send_subject': 'Subject {event}',
        'send_message': 'Message {voucher_list}',
        'email': 'empty',
        'name': 'csv:H',
    })
    with pytest.raises(DataImportError) as excinfo:
        import_vouchers.apply(
            args=(event.pk, inputfile_with_recipients().id, settings, 'en', user.pk)
        ).get()
    assert 'This field is required if you enable email sending.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_send_vouchers(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    settings.update({
        'send': True,
        'send_subject': 'Subject {event}',
        'send_message': 'Message {voucher_list}',
        'email': 'csv:G',
        'name': 'csv:H',
    })
    with mock.patch('pretix.base.services.modelimport.vouchers_send') as send_mock:
        import_vouchers.apply(
            args=(event.pk, inputfile_with_recipients().id, settings, 'en', user.pk)
        ).get()
    assert event.vouchers.count() == 2
    send_mock.assert_called_once()
    kwargs = send_mock.call_args.kwargs
    assert kwargs['subject'] == settings['send_subject']
    assert kwargs['message'] == settings['send_message']
    assert kwargs['user'] == user.pk
    assert kwargs['recipients'] == [
        {'email': 'alice@example.org', 'name': 'Alice', 'number': 1},
        {'email': 'bob@example.org', 'name': 'Bob', 'number': 1},
    ]


@pytest.mark.django_db
@scopes_disabled()
def test_import_send_rejects_invalid_email(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    settings.update({
        'send': True,
        'send_subject': 'Subject {event}',
        'send_message': 'Message {voucher_list}',
        'email': 'csv:G',
        'name': 'csv:H',
    })
    with pytest.raises(DataImportError) as excinfo:
        import_vouchers.apply(
            args=(event.pk, inputfile_with_invalid_email().id, settings, 'en', user.pk)
        ).get()
    assert 'Enter a valid email address.' in str(excinfo.value)


@pytest.mark.django_db
@scopes_disabled()
def test_import_send_disabled_does_not_send(event, item, user):
    settings = dict(DEFAULT_SETTINGS)
    settings.update({
        'send': False,
        'send_subject': 'Subject {event}',
        'send_message': 'Message {voucher_list}',
        'email': 'csv:G',
        'name': 'csv:H',
    })
    with mock.patch('pretix.base.services.modelimport.vouchers_send') as send_mock:
        import_vouchers.apply(
            args=(event.pk, inputfile_with_recipients().id, settings, 'en', user.pk)
        ).get()
    assert event.vouchers.count() == 2
    send_mock.assert_not_called()
