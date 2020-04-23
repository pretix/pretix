import time
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils.timezone import now
from django_scopes import scope
from freezegun import freeze_time

from pretix.base.models import Checkin, Event, Order, OrderPosition, Organizer
from pretix.base.services.checkin import (
    CheckInError, RequiredQuestionsError, perform_checkin,
)


@pytest.fixture(scope='function')
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.banktransfer'
    )
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
def test_checkin_invalid_product(position, clist):
    clist.all_products = False
    clist.save()
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'product'
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
def test_unpaid_include_pending_ignore(position, clist):
    o = position.order
    o.status = Order.STATUS_PENDING
    o.save()
    clist.include_pending = True
    clist.save()
    perform_checkin(position, clist, {}, ignore_unpaid=True)


@pytest.mark.django_db
def test_unpaid_ignore_without_include_pendung(position, clist):
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
    perform_checkin(position, clist, {})

    perform_checkin(position, clist, {}, force=True, nonce='bla')
    perform_checkin(position, clist, {}, force=True, nonce='bla')

    assert position.checkins.count() == 2
    assert position.checkins.first().forced
    assert position.order.all_logentries().count() == 2


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
    assert excinfo.value.code == 'rules'

    clist.rules = {'and': [True, True]}
    clist.save()
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
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'rules'

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
    assert excinfo.value.code == 'rules'

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
    perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_scan_number(position, clist):
    # Ticket is valid three times
    clist.allow_multiple_entries = True
    clist.rules = {"<": [{"var": "entries_number"}, 3]}
    clist.save()
    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {})
    perform_checkin(position, clist, {}, type=Checkin.TYPE_EXIT)
    perform_checkin(position, clist, {})
    with pytest.raises(CheckInError) as excinfo:
        perform_checkin(position, clist, {})
    assert excinfo.value.code == 'rules'


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
        perform_checkin(position, clist, {})
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'

    with freeze_time("2020-01-01 22:50:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'

    with freeze_time("2020-01-01 23:10:00"):
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'


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
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-03 10:00:00"):
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-03 22:50:00"):
        perform_checkin(position, clist, {})

    with freeze_time("2020-01-03 23:50:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'


@pytest.mark.django_db
def test_rules_time_isafter_tolerance(event, position, clist):
    # Ticket is valid starting 10 minutes before admission time
    event.settings.timezone = 'Europe/Berlin'
    event.date_admission = event.timezone.localize(datetime(2020, 1, 1, 12, 0, 0))
    event.save()
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["date_admission"]}, 10]}
    clist.save()
    with freeze_time("2020-01-01 10:45:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'

    with freeze_time("2020-01-01 10:51:00"):
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_time_isafter_no_tolerance(event, position, clist):
    # Ticket is valid only after admission time
    event.settings.timezone = 'Europe/Berlin'
    event.date_from = event.timezone.localize(datetime(2020, 1, 1, 12, 0, 0))
    # also tests that date_admission falls back to date_from
    event.save()
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["date_admission"]}]}
    clist.save()
    with freeze_time("2020-01-01 10:51:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'

    with freeze_time("2020-01-01 11:01:00"):
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_time_isbefore_with_tolerance(event, position, clist):
    # Ticket is valid until 10 minutes after end time
    event.settings.timezone = 'Europe/Berlin'
    event.date_to = event.timezone.localize(datetime(2020, 1, 1, 12, 0, 0))
    event.save()
    clist.rules = {"isBefore": [{"var": "now"}, {"buildTime": ["date_to"]}, 10]}
    clist.save()
    with freeze_time("2020-01-01 11:11:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'

    with freeze_time("2020-01-01 11:09:00"):
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_time_isafter_custom_time(event, position, clist):
    # Ticket is valid starting at a custom time
    event.settings.timezone = 'Europe/Berlin'
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["custom", "2020-01-01T22:00:00.000Z"]}, None]}
    clist.save()
    with freeze_time("2020-01-01 21:55:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'

    with freeze_time("2020-01-01 22:05:00"):
        perform_checkin(position, clist, {})


@pytest.mark.django_db
def test_rules_isafter_subevent(position, clist, event):
    event.has_subevents = True
    event.save()
    event.settings.timezone = 'Europe/Berlin'
    se1 = event.subevents.create(name="Foo", date_from=event.timezone.localize(datetime(2020, 2, 1, 12, 0, 0)))
    position.subevent = se1
    position.save()
    clist.rules = {"isAfter": [{"var": "now"}, {"buildTime": ["date_admission"]}]}
    clist.save()
    with freeze_time("2020-02-01 10:51:00"):
        with pytest.raises(CheckInError) as excinfo:
            perform_checkin(position, clist, {})
        assert excinfo.value.code == 'rules'

    with freeze_time("2020-02-01 11:01:00"):
        perform_checkin(position, clist, {})


@pytest.mark.django_db(transaction=True)
def test_position_queries(django_assert_num_queries, position, clist):
    with django_assert_num_queries(11) as captured:
        perform_checkin(position, clist, {})
    assert 'BEGIN' in captured[0]['sql']
    if 'sqlite' not in settings.DATABASES['default']['ENGINE']:
        assert 'FOR UPDATE' in captured[1]['sql']
