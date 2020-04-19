from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Order, OrderPosition, Organizer
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
    c = event.items.create(name="Ticket", default_price=3, admission=True)
    return c


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

    perform_checkin(position, clist, {}, force=True)

    assert position.checkins.count() == 1
    assert position.order.all_logentries().count() == 2
