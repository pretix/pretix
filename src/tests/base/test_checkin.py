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
import time
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils.timezone import now, override
from django_scopes import scope
from freezegun import freeze_time

from pretix.base.models import Checkin, Event, Order, OrderPosition, Organizer
from pretix.base.services.checkin import (
    CheckInError, RequiredQuestionsError, SQLLogic, perform_checkin,
    process_exit_all,
)


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer'
    )
    event.settings.timezone = 'Europe/Berlin'
    with scope(organizer=o):
        yield event


@pytest.fixture
def clist(event):
    c = event.checkin_lists.create(name="Default", all_products=True)
    return c


@pytest.fixture
def item(event):
    return event.items.create(name="Ticket", default_price=3, admission=True)


@pytest.fixture
def position(event, item):
    order = Order.objects.create(
        code='FOO', event=event, email='dummy@dummy.test',
        status=Order.STATUS_PAID, locale='en',
        datetime=now() - timedelta(days=4),
        expires=now() - timedelta(hours=4) + timedelta(days=10),
        total=Decimal('23.00'),
    )
    return OrderPosition.objects.create(
        order=order, item=item, variation=None,
        price=Decimal("23.00"), attendee_name_parts={"full_name": "Peter"}, positionid=1
    )


@pytest.mark.django_db
def test_checkin_valid(position, clist):
    perform_checkin(position, clist, {})
    assert position.checkins.count() == 1


@pytest.mark.django_db
def test_checkin_canceled_order(position, clist):
    o = position.order
    o.status = Order.STATUS_CANCELED
    o.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'unpaid'
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {}, canceled_supported=True)
    assert excinfo.value.code == 'canceled'
    assert position.checkins.count() == 0

    o.status = Order.STATUS_EXPIRED
    o.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {}, canceled_supported=True)
    assert excinfo.value.code == 'canceled'
    assert position.checkins.count() == 0
    perform_checkin(position, clist, {}, canceled_supported=True, force=True)
    assert position.checkins.count() == 1


@pytest.mark.django_db
def test_checkin_canceled_position(position, clist):
    position.canceled = True
    position.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'unpaid'
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {}, canceled_supported=True)
    assert excinfo.value.code == 'canceled'
    assert position.checkins.count() == 0


@pytest.mark.django_db
def test_checkin_blocked_position(position, clist):
    position.blocked = ["admin"]
    position.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'blocked'
    assert position.checkins.count() == 0
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
    assert excinfo.value.code == 'blocked'
    assert position.checkins.count() == 0
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT, force=True)
    assert position.checkins.count() == 1


@pytest.mark.django_db
def test_checkin_valid_from(event, position, clist):
    position.valid_from = datetime(2020, 1, 1, 12, 0, 0, tzinfo=event.timezone)
    position.save()
    with freeze_time("2020-01-01 10:45:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'invalid_time'
        assert excinfo.value.reason == 'This ticket is only valid after 2020-01-01 12:00.'
        assert position.checkins.count() == 0
        # Force is allowed
        perform_checkin(position, clist, {}, force=True)
        assert position.checkins.count() == 1

        perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
        assert position.checkins.count() == 2


@pytest.mark.django_db
def test_checkin_valid_until(event, position, clist):
    position.valid_until = datetime(2020, 1, 1, 9, 0, 0, tzinfo=event.timezone)
    position.save()
    with freeze_time("2020-01-01 10:45:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'invalid_time'
        assert excinfo.value.reason == 'This ticket was only valid before 2020-01-01 09:00.'
        assert position.checkins.count() == 0
        # Force is allowed
        perform_checkin(position, clist, {}, force=True)
        assert position.checkins.count() == 1

        perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
        assert position.checkins.count() == 2


@pytest.mark.django_db
def test_checkin_invalid_product(position, clist):
    clist.all_products = False
    clist.allow_multiple_entries = True
    clist.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'product'

    perform_checkin(position, clist, {}, force=True)

    clist.limit_products.add(position.item)
    perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_checkin_invalid_subevent(position, clist, event):
    event.has_subevents = True
    event.save()
    se1 = event.subevents.create(name="Foo", date_from=event.date_from)
    se2 = event.subevents.create(name="Foo", date_from=event.date_from)
    position.subevent = se1
    position.save()
    clist.subevent = se2
    clist.save()

    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'product'

    perform_checkin(position, clist, {}, force=True)


@pytest.mark.django_db
def test_checkin_all_subevents(position, clist, event):
    event.has_subevents = True
    event.save()
    se1 = event.subevents.create(name="Foo", date_from=event.date_from)
    position.subevent = se1
    position.save()
    perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_unpaid(position, clist):
    o = position.order
    o.status = Order.STATUS_PENDING
    o.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'unpaid'


@pytest.mark.django_db
def test_unpaid_but_valid(position, clist):
    o = position.order
    o.status = Order.STATUS_PENDING
    o.valid_if_pending = True
    o.save()
    clist.include_pending = False
    clist.save()
    perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_require_approval(position, clist):
    o = position.order
    o.status = Order.STATUS_PENDING
    o.require_approval = True
    o.save()
    clist.include_pending = False
    clist.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {}, ignore_unpaid=True)
    assert excinfo.value.code == 'unpaid'
    perform_checkin(position, clist, {}, ignore_unpaid=True, force=True)
    assert position.checkins.count() == 1


@pytest.mark.django_db
def test_unpaid_include_pending_ignore(position, clist):
    o = position.order
    o.status = Order.STATUS_PENDING
    o.save()
    clist.include_pending = True
    clist.save()
    perform_checkin(position, clist, {}, ignore_unpaid=True)


@pytest.mark.django_db
def test_unpaid_ignore_without_include_pending(position, clist):
    o = position.order
    o.status = Order.STATUS_PENDING
    o.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'unpaid'


@pytest.mark.django_db
def test_unpaid_force(position, clist):
    o = position.order
    o.status = Order.STATUS_PENDING
    o.save()
    perform_checkin(position, clist, {}, force=True)


@pytest.mark.django_db
def test_required_question_missing(event, position, clist):
    q = event.questions.create(
        question="Quo vadis?",
        type="S",
        required=True,
        ask_during_checkin=True,
    )
    q.items.add(position.item)
    with pytest.raises(RequiredQuestionsError) as excinfo:
        perform_checkin(position, clist, {}, questions_supported=True)
    assert excinfo.value.code == 'incomplete'
    assert excinfo.value.questions == [q]


@pytest.mark.django_db
def test_required_question_missing_but_not_supported(event, position, clist):
    q = event.questions.create(
        question="Quo vadis?",
        type="S",
        required=True,
        ask_during_checkin=True,
    )
    q.items.add(position.item)
    perform_checkin(position, clist, {}, questions_supported=False)


@pytest.mark.django_db
def test_required_question_missing_but_forced(event, position, clist):
    q = event.questions.create(
        question="Quo vadis?",
        type="S",
        required=True,
        ask_during_checkin=True,
    )
    q.items.add(position.item)
    perform_checkin(position, clist, {}, questions_supported=True, force=True)


@pytest.mark.django_db
def test_optional_question_missing(event, position, clist):
    q = event.questions.create(
        question="Quo vadis?",
        type="S",
        required=False,
        ask_during_checkin=True,
    )
    q.items.add(position.item)
    with pytest.raises(RequiredQuestionsError) as excinfo:
        perform_checkin(position, clist, {}, questions_supported=True)
    assert excinfo.value.code == 'incomplete'
    assert excinfo.value.questions == [q]


@pytest.mark.django_db
def test_required_online_question_missing(event, position, clist):
    q = event.questions.create(
        question="Quo vadis?",
        type="S",
        required=True,
        ask_during_checkin=False,
    )
    q.items.add(position.item)
    perform_checkin(position, clist, {}, questions_supported=True)


@pytest.mark.django_db
def test_question_filled_previously(event, position, clist):
    q = event.questions.create(
        question="Quo vadis?",
        type="S",
        required=True,
        ask_during_checkin=True,
    )
    q.items.add(position.item)
    position.answers.create(question=q, answer='Foo')
    perform_checkin(position, clist, {}, questions_supported=True)


@pytest.mark.django_db
def test_question_filled(event, position, clist):
    q = event.questions.create(
        question="Quo vadis?",
        type="S",
        required=True,
        ask_during_checkin=True,
    )
    q.items.add(position.item)
    perform_checkin(position, clist, {q: 'Foo'}, questions_supported=True)
    a = position.answers.get()
    assert a.question == q
    assert a.answer == 'Foo'


@pytest.mark.django_db
def test_single_entry(position, clist):
    perform_checkin(position, clist, {})

    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'already_redeemed'

    assert position.checkins.count() == 1


@pytest.mark.django_db
def test_single_entry_repeat_nonce(position, clist):
    perform_checkin(position, clist, {}, nonce='foo')
    perform_checkin(position, clist, {}, nonce='foo')

    assert position.checkins.count() == 1


@pytest.mark.django_db
def test_multi_entry(position, clist):
    clist.allow_multiple_entries = True
    clist.save()
    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {})

    assert position.checkins.count() == 2


@pytest.mark.django_db
def test_multi_entry_repeat_nonce(position, clist):
    clist.allow_multiple_entries = True
    clist.save()
    perform_checkin(position, clist, {}, nonce='foo')
    perform_checkin(position, clist, {}, nonce='foo')

    assert position.checkins.count() == 1


@pytest.mark.django_db
def test_single_entry_forced_reentry(position, clist):
    perform_checkin(position, clist, {}, force=True)

    perform_checkin(position, clist, {}, force=True, nonce='bla')
    perform_checkin(position, clist, {}, force=True, nonce='bla')

    assert position.checkins.count() == 2
    assert not position.checkins.last().forced
    assert position.checkins.first().forced
    assert position.order.all_logentries().count() == 2


@pytest.mark.django_db
def test_exit_does_not_invalidate(position, clist):
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)

    assert position.checkins.count() == 3


@pytest.mark.django_db
def test_multi_exit(position, clist):
    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)

    assert position.checkins.count() == 3


@pytest.mark.django_db
def test_single_entry_after_exit_ordered_by_date(position, clist):
    dt1 = now() - timedelta(minutes=10)
    dt2 = now() - timedelta(minutes=5)
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT, datetime=dt2)
    time.sleep(1)
    perform_checkin(position, clist, {}, datetime=dt1)
    perform_checkin(position, clist, {})

    assert position.checkins.count() == 3


@pytest.mark.django_db
def test_single_entry_after_exit(position, clist):
    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
    perform_checkin(position, clist, {})

    assert position.checkins.count() == 3


@pytest.mark.django_db
def test_single_entry_after_exit_forbidden(position, clist):
    clist.allow_entry_after_exit = False
    clist.save()

    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'already_redeemed'

    assert position.checkins.count() == 2


@pytest.mark.django_db
def test_rules_simple(position, clist):
    clist.rules = {'and': [False, True]}
    clist.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    perform_checkin(position, clist, {}, type='exit')
    assert excinfo.value.code == 'rules'

    clist.rules = {'and': [True, True]}
    clist.save()

    assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
    perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_product(event, position, clist):
    i2 = event.items.create(name="Ticket", default_price=3, admission=True)
    clist.rules = {
        "inList": [
            {"var": "product"}, {
                "objectList": [
                    {"lookup": ["product", str(i2.pk), "Ticket"]},
                ]
            }
        ]
    }
    clist.save()
    assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'rules'
    assert 'Ticket type not allowed' in str(excinfo.value)

    clist.rules = {
        "inList": [
            {"var": "product"}, {
                "objectList": [
                    {"lookup": ["product", str(i2.pk), "Ticket"]},
                    {"lookup": ["product", str(position.item.pk), "Ticket"]},
                ]
            }
        ]
    }
    clist.save()
    assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
    perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_variation(item, position, clist):
    v1 = item.variations.create(value="A")
    v2 = item.variations.create(value="B")
    position.variation = v2
    position.save()
    clist.rules = {
        "inList": [
            {"var": "variation"}, {
                "objectList": [
                    {"lookup": ["variation", str(v1.pk), "Ticket – A"]},
                ]
            }
        ]
    }
    clist.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
    assert excinfo.value.code == 'rules'
    assert 'Ticket type not allowed' in str(excinfo.value)

    clist.rules = {
        "inList": [
            {"var": "variation"}, {
                "objectList": [
                    {"lookup": ["variation", str(v1.pk), "Ticket – A"]},
                    {"lookup": ["variation", str(v2.pk), "Ticket – B"]},
                ]
            }
        ]
    }
    clist.save()
    assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
    perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_scan_number(position, clist):
    # Ticket is valid three times
    clist.allow_multiple_entries = True
    clist.rules = {"<": [{"var": "entries_number"}, 3]}
    clist.save()
    assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
    assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
    perform_checkin(position, clist, {})
    assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'rules'
    assert 'Maximum number of entries' in str(excinfo.value)


@pytest.mark.django_db
def test_rules_scan_minutes_since_last(position, clist):
    # Ticket is valid unlimited times, but you always need to wait 3 hours
    clist.allow_multiple_entries = True
    clist.rules = {"or": [{"<=": [{"var": "minutes_since_last_entry"}, -1]}, {">": [{"var": "minutes_since_last_entry"}, 60 * 3]}]}
    clist.save()

    with freeze_time("2020-01-01 10:00:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-01 12:55:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Minimum time since last entry' in str(excinfo.value)

    with freeze_time("2020-01-01 13:01:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-01 15:55:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Minimum time since last entry' in str(excinfo.value)

    with freeze_time("2020-01-01 16:02:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_scan_minutes_since_fist(position, clist):
    # Ticket is valid unlimited times, but you always need to wait 3 hours
    clist.allow_multiple_entries = True
    clist.rules = {"or": [{"<=": [{"var": "minutes_since_first_entry"}, -1]}, {"<": [{"var": "minutes_since_first_entry"}, 60 * 3]}]}
    clist.save()

    with freeze_time("2020-01-01 10:00:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-01 12:55:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-01 13:01:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Maximum time since first entry' in str(excinfo.value)


@pytest.mark.django_db
def test_rules_scan_today(event, position, clist):
    # Ticket is valid three times per day
    event.settings.timezone = 'Europe/Berlin'
    clist.allow_multiple_entries = True
    clist.rules = {"<": [{"var": "entries_today"}, 3]}
    clist.save()
    with freeze_time("2020-01-01 10:00:00"):
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Maximum number of entries today' in str(excinfo.value)

    with freeze_time("2020-01-01 22:50:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Maximum number of entries today' in str(excinfo.value)

    with freeze_time("2020-01-01 23:10:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Maximum number of entries today' in str(excinfo.value)


@pytest.mark.django_db
def test_rules_scan_days(event, position, clist):
    # Ticket is valid unlimited times, but only on two arbitrary days
    event.settings.timezone = 'Europe/Berlin'
    clist.allow_multiple_entries = True
    clist.rules = {"or": [{">": [{"var": "entries_today"}, 0]}, {"<": [{"var": "entries_days"}, 2]}]}
    clist.save()
    with freeze_time("2020-01-01 10:00:00"):
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-03 10:00:00"):
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-03 22:50:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-03 23:50:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Maximum number of days with an entry exceeded.' in str(excinfo.value)


@pytest.mark.django_db
def test_rules_time_isafter_tolerance(event, position, clist):
    # Ticket is valid starting 10 minutes before admission time
    event.settings.timezone = 'Europe/Berlin'
    event.date_admission = datetime(2020, 1, 1, 12, 0, 0, tzinfo=event.timezone)
    event.save()
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["date_admission"]}, 10]}
    clist.save()
    with freeze_time("2020-01-01 10:45:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed after 11:50' in str(excinfo.value)

    with freeze_time("2020-01-01 10:51:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_time_isafter_no_tolerance(event, position, clist):
    # Ticket is valid only after admission time
    event.settings.timezone = 'Europe/Berlin'
    event.date_from = datetime(2020, 1, 1, 12, 0, 0, tzinfo=event.timezone)
    # also tests that date_admission falls back to date_from
    event.save()
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["date_admission"]}]}
    clist.save()
    with freeze_time("2020-01-01 10:51:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed after 12:00' in str(excinfo.value)

    with freeze_time("2020-01-01 11:01:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_time_isbefore_with_tolerance(event, position, clist):
    # Ticket is valid until 10 minutes after end time
    event.settings.timezone = 'Europe/Berlin'
    event.date_to = datetime(2020, 1, 1, 12, 0, 0, tzinfo=event.timezone)
    event.save()
    clist.rules = {"isBefore": [{"var": "now"}, {"buildTime": ["date_to"]}, 10]}
    clist.save()
    with freeze_time("2020-01-01 11:11:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed before 12:10' in str(excinfo.value)

    with freeze_time("2020-01-01 11:09:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_time_isafter_custom_time(event, position, clist):
    # Ticket is valid starting at a custom time
    event.settings.timezone = 'Europe/Berlin'
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["customtime", "22:00:00"]}, None]}
    clist.save()
    with freeze_time("2020-01-01 21:55:00+01:00"), override(event.timezone):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed after 22:00' in str(excinfo.value)

    with freeze_time("2020-01-01 22:05:00+01:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_time_isafter_custom_datetime(event, position, clist):
    # Ticket is valid starting at a custom time
    event.settings.timezone = 'Europe/Berlin'
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["custom", "2020-01-01T23:00:00.000+01:00"]}, None]}
    clist.save()
    with freeze_time("2020-01-01 21:55:00+00:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'

    with freeze_time("2020-01-01 22:05:00+00:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_isafter_subevent(position, clist, event):
    event.has_subevents = True
    event.save()
    event.settings.timezone = 'Europe/Berlin'
    se1 = event.subevents.create(name="Foo", date_from=datetime(2020, 2, 1, 12, 0, 0, tzinfo=event.timezone))
    position.subevent = se1
    position.save()
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["date_admission"]}]}
    clist.save()
    with freeze_time("2020-02-01 10:51:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed after 12:00' in str(excinfo.value)

    with freeze_time("2020-02-01 11:01:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_time_isoweekday(event, position, clist):
    # Ticket is valid starting at a custom time
    event.settings.timezone = 'Europe/Berlin'
    clist.rules = {"==": [{"var": "now_isoweekday"}, 6]}
    clist.save()
    with freeze_time("2022-04-06 21:55:00+01:00"):
        assert not OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'week day is not Saturday' in str(excinfo.value)

    with freeze_time("2022-04-09 22:05:00+01:00"):
        assert OrderPosition.objects.filter(SQLLogic(clist).apply(clist.rules), pk=position.pk).exists()
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_reasoning_prefer_close_date(event, position, clist):
    # Ticket is valid starting at a custom time
    event.settings.timezone = 'Europe/Berlin'
    clist.rules = {
        "or": [
            {
                "and": [
                    {"isAfter": [{"var": "now"}, {"buildTime": ["custom", "2020-01-01T10:00:00.000Z"]}, None]},
                    {"isBefore": [{"var": "now"}, {"buildTime": ["custom", "2020-01-01T18:00:00.000Z"]}, None]},
                ]
            },
            {
                "and": [
                    {"isAfter": [{"var": "now"}, {"buildTime": ["custom", "2020-01-02T10:00:00.000Z"]}, None]},
                    {"isBefore": [{"var": "now"}, {"buildTime": ["custom", "2020-01-02T18:00:00.000Z"]}, None]},
                ]
            },
        ]
    }
    clist.save()
    with freeze_time("2020-01-01 09:00:00Z"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed after 11:00' in str(excinfo.value)

    with freeze_time("2020-01-01 20:00:00Z"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed before 19:00' in str(excinfo.value)

    with freeze_time("2020-01-02 09:00:00Z"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed after 11:00' in str(excinfo.value)

    with freeze_time("2020-01-03 18:00:00Z"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed before 2020-01-02 19:00' in str(excinfo.value)


@pytest.mark.django_db
def test_rules_reasoning_prefer_date_over_product(event, position, clist):
    i2 = event.items.create(name="Ticket", default_price=3, admission=True)
    clist.rules = {
        "or": [
            {
                "inList": [
                    {"var": "product"}, {
                        "objectList": [
                            {"lookup": ["product", str(i2.pk), "Ticket"]},
                        ]
                    }
                ]
            },
            {
                "and": [
                    {"isAfter": [{"var": "now"}, {"buildTime": ["custom", "2020-01-02T10:00:00.000Z"]}, None]},
                    {"isBefore": [{"var": "now"}, {"buildTime": ["custom", "2020-01-02T18:00:00.000Z"]}, None]},
                ]
            }
        ]
    }
    clist.save()

    with freeze_time("2020-01-02 20:00:00Z"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Only allowed before 19:00' in str(excinfo.value)


@pytest.mark.django_db
def test_rules_reasoning_prefer_number_over_date(event, position, clist):
    clist.rules = {
        "and": [
            {"isAfter": [{"var": "now"}, {"buildTime": ["custom", "2020-01-02T10:00:00.000Z"]}, None]},
            {"isBefore": [{"var": "now"}, {"buildTime": ["custom", "2020-01-02T18:00:00.000Z"]}, None]},
            {">": [{"var": "entries_today"}, 3]}
        ]
    }
    clist.save()

    with freeze_time("2020-01-01 20:00:00Z"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'
        assert 'Minimum number of entries today exceeded' in str(excinfo.value)


@pytest.mark.django_db(transaction=True)
def test_position_queries(django_assert_num_queries, position, clist):
    with django_assert_num_queries(12 if 'sqlite' in settings.DATABASES['default']['ENGINE'] else 11) as captured:
        perform_checkin(position, clist, {})
    if 'sqlite' not in settings.DATABASES['default']['ENGINE']:
        assert any('FOR UPDATE' in s['sql'] for s in captured)


@pytest.mark.django_db(transaction=True)
def test_auto_checkout_at_correct_time(event, position, clist):
    clist.exit_all_at = datetime(2020, 1, 2, 3, 0, tzinfo=event.timezone)
    clist.save()
    with freeze_time("2020-01-01 10:00:00+01:00"):
        perform_checkin(position, clist, {})
    with freeze_time("2020-01-02 02:55:00+01:00"):
        process_exit_all(sender=None)
    assert position.checkins.count() == 1
    with freeze_time("2020-01-02 03:05:00+01:00"):
        process_exit_all(sender=None)
    assert clist.inside_count == 0
    assert position.checkins.count() == 2
    assert position.checkins.first().type == Checkin.TYPE_EXIT
    clist.refresh_from_db()
    assert clist.exit_all_at == datetime(2020, 1, 3, 3, 0, tzinfo=event.timezone)


@pytest.mark.django_db(transaction=True)
def test_auto_check_out_only_if_checked_in(event, position, clist):
    clist.exit_all_at = datetime(2020, 1, 2, 3, 0, tzinfo=event.timezone)
    clist.save()
    with freeze_time("2020-01-02 03:05:00+01:00"):
        process_exit_all(sender=None)
    assert position.checkins.count() == 0

    with freeze_time("2020-01-02 04:05:00+01:00"):
        perform_checkin(position, clist, {})
    with freeze_time("2020-01-02 04:10:00+01:00"):
        perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)

    with freeze_time("2020-01-03 03:05:00+01:00"):
        process_exit_all(sender=None)
    assert position.checkins.count() == 2


@pytest.mark.django_db(transaction=True)
def test_auto_check_out_only_if_checked_in_before_exit_all_at(event, position, clist):
    clist.exit_all_at = datetime(2020, 1, 2, 3, 0, tzinfo=event.timezone)
    clist.save()
    with freeze_time("2020-01-02 04:05:00+01:00"):
        perform_checkin(position, clist, {})

    process_exit_all(sender=None)
    assert position.checkins.count() == 1


@pytest.mark.django_db(transaction=True)
def test_auto_check_out_dst(event, position, clist):
    event.settings.timezone = 'Europe/Berlin'

    # Survive across a shift that doesn't affect the time in question
    clist.exit_all_at = datetime(2021, 3, 28, 1, 0, tzinfo=event.timezone)
    clist.save()
    with freeze_time(clist.exit_all_at + timedelta(minutes=5)):
        process_exit_all(sender=None)
    clist.refresh_from_db()
    assert clist.exit_all_at.astimezone(event.timezone) == datetime(2021, 3, 29, 1, 0, tzinfo=event.timezone)

    # Survive across a shift that makes the time in question ambigous
    clist.exit_all_at = datetime(2021, 10, 30, 2, 30, tzinfo=event.timezone)
    clist.save()
    with freeze_time(clist.exit_all_at + timedelta(minutes=5)):
        process_exit_all(sender=None)
    clist.refresh_from_db()
    assert clist.exit_all_at.astimezone(event.timezone) == datetime(2021, 10, 31, 2, 30, tzinfo=event.timezone)
    with freeze_time(clist.exit_all_at + timedelta(minutes=5)):
        process_exit_all(sender=None)
    clist.refresh_from_db()
    assert clist.exit_all_at.astimezone(event.timezone) == datetime(2021, 11, 1, 2, 30, tzinfo=event.timezone)

    # Moves back after a shift that makes the time in question non-existant
    clist.exit_all_at = datetime(2021, 3, 27, 2, 30, tzinfo=event.timezone)
    clist.save()
    with freeze_time(clist.exit_all_at + timedelta(minutes=5)):
        process_exit_all(sender=None)
    clist.refresh_from_db()
    assert clist.exit_all_at.astimezone(event.timezone) == datetime(2021, 3, 28, 3, 30, tzinfo=event.timezone)
    with freeze_time(clist.exit_all_at + timedelta(minutes=5)):
        process_exit_all(sender=None)
    clist.refresh_from_db()
    assert clist.exit_all_at.astimezone(event.timezone) == datetime(2021, 3, 29, 2, 30, tzinfo=event.timezone)
    with freeze_time(clist.exit_all_at + timedelta(minutes=5)):
        process_exit_all(sender=None)
    clist.refresh_from_db()
    assert clist.exit_all_at.astimezone(event.timezone) == datetime(2021, 3, 30, 2, 30, tzinfo=event.timezone)
