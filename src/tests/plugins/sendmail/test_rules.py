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
from zoneinfo import ZoneInfo

import pytest
from django.core import mail as djmail
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import InvoiceAddress, Order
from pretix.plugins.sendmail.models import Rule, ScheduledMail
from pretix.plugins.sendmail.signals import sendmail_run_rules


@pytest.mark.django_db
def test_sendmail_rule_create_single(event):
    dt = now()
    r = Rule.objects.create(event=event, subject='dummy mail', template='mail body', send_date=dt)

    mails = ScheduledMail.objects.filter(rule=r)
    assert mails.count() == 1

    mail = mails.get()
    assert mail.computed_datetime == dt


dt_now = now()
NZ = ZoneInfo('NZ')
Berlin = ZoneInfo('Europe/Berlin')


@pytest.mark.django_db
@pytest.mark.parametrize(
    "event_from,event_to,event_tz,rule,expected",
    [

        # Tests for all possible configurations of relative times
        (  # "Absolute"
            None,
            None,
            'UTC',
            Rule(date_is_absolute=True, send_date=dt_now),
            dt_now
        ),
        (  # "Relative, after event start"
            None,
            None,
            'UTC',
            Rule(date_is_absolute=False, offset_is_after=True, send_offset_days=1, send_offset_time=datetime.time(hour=9)),
            (dt_now + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        ),
        (  # "Relative, before event start"
            datetime.datetime(2021, 5, 17, 12, 14, 0, tzinfo=datetime.timezone.utc),
            None,
            'UTC',
            Rule(date_is_absolute=False, send_offset_days=2, send_offset_time=datetime.time(hour=0)),
            datetime.datetime(2021, 5, 15, 0, tzinfo=datetime.timezone.utc)
        ),
        (  # "Relative, after event end"
            datetime.datetime(2021, 5, 17, 18, tzinfo=datetime.timezone.utc),
            datetime.datetime(2021, 5, 18, 5, tzinfo=datetime.timezone.utc),
            'UTC',
            Rule(date_is_absolute=False, offset_to_event_end=True, offset_is_after=True, send_offset_days=1, send_offset_time=datetime.time(hour=10)),
            datetime.datetime(2021, 5, 19, 10, tzinfo=datetime.timezone.utc)
        ),
        (  # "Relative, before event end"
            datetime.datetime(2021, 5, 17, 18, tzinfo=datetime.timezone.utc),
            datetime.datetime(2021, 5, 22, 5, tzinfo=datetime.timezone.utc),
            'UTC',
            Rule(date_is_absolute=False, offset_to_event_end=True, offset_is_after=False, send_offset_days=1, send_offset_time=datetime.time(hour=10)),
            datetime.datetime(2021, 5, 21, 10, tzinfo=datetime.timezone.utc)
        ),

        # Tests for timezone quirks
        (  # Test sending on leap day
            datetime.datetime(2020, 2, 27, 9, tzinfo=datetime.timezone.utc),
            None,
            'UTC',
            Rule(date_is_absolute=False, offset_is_after=True, send_offset_days=2, send_offset_time=datetime.time(hour=9)),
            datetime.datetime(2020, 2, 29, 9, tzinfo=datetime.timezone.utc)
        ),
        (  # Test timezone far off from UTC
            datetime.datetime(2021, 5, 17, 22, tzinfo=NZ),
            None,
            'NZ',
            Rule(date_is_absolute=False, offset_is_after=True, send_offset_days=1, send_offset_time=datetime.time(hour=9)),
            datetime.datetime(2021, 5, 18, 9, tzinfo=NZ)
        ),
        (  # Test across DST change
            datetime.datetime(2021, 10, 29, 16, 30, tzinfo=Berlin),
            None,
            'Europe/Berlin',
            Rule(date_is_absolute=False, offset_is_after=True, send_offset_days=4, send_offset_time=datetime.time(hour=2, minute=30)),
            datetime.datetime(2021, 11, 2, 2, 30, tzinfo=Berlin)
        ),
        (  # Test ambiguous time at DST change
            datetime.datetime(2021, 10, 29, 18, 30, tzinfo=Berlin),
            None,
            'Europe/Berlin',
            Rule(date_is_absolute=False, offset_is_after=True, send_offset_days=2, send_offset_time=datetime.time(hour=2, minute=30)),
            datetime.datetime(2021, 10, 31, 1, 30, tzinfo=datetime.timezone.utc)
        ),
        (  # Test non-existing time at DST change
            datetime.datetime(2021, 3, 29, 14, 30, tzinfo=Berlin),
            None,
            'Europe/Berlin',
            Rule(date_is_absolute=False, offset_is_after=False, send_offset_days=1, send_offset_time=datetime.time(hour=2, minute=30)),
            datetime.datetime(2021, 3, 28, 1, 30, tzinfo=datetime.timezone.utc)
        ),

    ])
def test_sendmail_rule_send_time(event_from, event_to, event_tz, rule, expected, event):
    if event_from:
        event.date_from = event_from
        event.save()

    if event_to:
        event.date_to = event_to
        event.save()

    event.settings.timezone = event_tz

    rule.event = event
    rule.save()
    m = ScheduledMail.objects.filter(rule=rule).get()

    assert m.computed_datetime.astimezone(event.timezone) == expected.astimezone(event.timezone)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_recompute(event):
    event.has_subevents = True
    event.save()
    se1 = event.subevents.create(name="meow", date_from=dt_now)

    rule = event.sendmail_rules.create(date_is_absolute=False, offset_is_after=False, send_offset_days=1,
                                       send_offset_time=datetime.time(4, 30))

    se1.date_from += datetime.timedelta(days=1)
    se1.save()

    expected = dt_now.replace(hour=4, minute=30, second=0, microsecond=0)

    sendmail_run_rules(None)

    m = ScheduledMail.objects.filter(rule=rule).first()
    assert m.computed_datetime.astimezone(datetime.timezone.utc) == expected


@pytest.mark.django_db
@pytest.mark.parametrize('send_to,amount_mails,recipients', [
    (Rule.CUSTOMERS, 1, ['dummy@dummy.test']),
    (Rule.ATTENDEES, 1, ['meow@dummy.test']),
    (Rule.BOTH, 2, ['dummy@dummy.test', 'meow@dummy.test']),
])
@scopes_disabled()
def test_sendmail_rule_send_order_vs_pos(send_to, amount_mails, recipients, order, event, item):
    djmail.outbox = []

    order.status = order.STATUS_PAID
    order.save()

    order.event.sendmail_rules.create(date_is_absolute=True, send_date=dt_now - datetime.timedelta(hours=1),
                                      send_to=send_to,
                                      subject='meow', template='meow meow meow')
    order.all_positions.create(item=item, price=0, attendee_email='meow@dummy.test')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == amount_mails

    _recipients = [mail.to[0] for mail in djmail.outbox]
    assert set(recipients) == set(_recipients)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_send_attendees_unset_mail(order, event, item):
    djmail.outbox = []
    order.status = order.STATUS_PAID
    order.save()

    order.all_positions.create(item=item, price=13)
    order.event.sendmail_rules.create(date_is_absolute=True, send_date=dt_now - datetime.timedelta(hours=1),
                                      send_to=Rule.ATTENDEES,
                                      subject='meow', template='meow meow meow')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 1
    mail = djmail.outbox[0]
    assert mail.to[0] == 'dummy@dummy.test'


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_send_both_same_email(order, event, item):
    djmail.outbox = []
    order.status = order.STATUS_PAID
    order.save()

    order.all_positions.create(item=item, price=13, attendee_email='dummy@dummy.test')
    order.event.sendmail_rules.create(date_is_absolute=True, send_date=dt_now - datetime.timedelta(hours=1),
                                      send_to=Rule.BOTH,
                                      subject='meow', template='meow meow meow')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 1


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_send_correct_subevent(order, event_series, subevent1, subevent2, item):
    djmail.outbox = []

    order.status = order.STATUS_PAID
    order.save()

    event_series.sendmail_rules.create(date_is_absolute=False, offset_is_after=False, send_offset_days=2,
                                       send_offset_time=datetime.time(9, 30), send_to=Rule.ATTENDEES,
                                       subject='meow', template='meow meow meow')
    p1 = order.all_positions.create(item=item, price=13, attendee_email='se1@dummy.test', subevent=subevent1)
    order.all_positions.create(item=item, price=23, attendee_email='se2@dummy.test', subevent=subevent2)

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 1

    assert djmail.outbox[0].to[0] == p1.attendee_email


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_send_correct_products(event, order, item, item2):
    djmail.outbox = []

    order.status = order.STATUS_PAID
    order.save()

    rule = event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1), send_to=Rule.ATTENDEES,
                                       subject='meow', template='meow meow meow', all_products=False)

    rule.limit_products.set([item])
    rule.save()

    p1 = order.all_positions.create(item=item, price=13, attendee_email='item1@dummy.test')
    order.all_positions.create(item=item2, price=13, attendee_email='item2@dummy.test')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 1

    assert djmail.outbox[0].to[0] == p1.attendee_email


@pytest.mark.django_db
@scopes_disabled()
def run_restriction_test(event, order, restrictions_pass=[], restrictions_fail=[]):
    for r in restrictions_pass:
        djmail.outbox = []
        event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1), restrict_to_status=[r],
                                    subject='meow', template='meow meow meow')
        sendmail_run_rules(None)

        assert len(djmail.outbox) == 1, f"email not sent for {r}"

    for r in restrictions_fail:
        djmail.outbox = []
        event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1), restrict_to_status=[r],
                                    subject='meow', template='meow meow meow')
        sendmail_run_rules(None)

        assert len(djmail.outbox) == 0, f"email sent for {r} unexpectedly"


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_restrictions_status_paid(event, order):
    order.status = Order.STATUS_PAID
    order.save()
    order.valid_if_pending = False
    restrictions_pass = ['p']
    restrictions_fail = ['e', 'c', 'n__not_pending_approval_and_not_valid_if_pending', 'n__pending_approval',
                         'n__valid_if_pending', 'n__pending_overdue']

    run_restriction_test(event, order, restrictions_pass, restrictions_fail)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_restrictions_status_pending(event, order):
    order.status = Order.STATUS_PENDING
    order.require_approval = False
    order.valid_if_pending = False
    order.save()
    restrictions_pass = ['n__not_pending_approval_and_not_valid_if_pending']
    restrictions_fail = ['p', 'e', 'c', 'n__pending_approval', "n__valid_if_pending", 'n__pending_overdue']

    run_restriction_test(event, order, restrictions_pass, restrictions_fail)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_restrictions_status_valid_pending(event, order):
    order.status = Order.STATUS_PENDING
    order.require_approval = False
    order.valid_if_pending = True
    order.save()
    restrictions_pass = ["n__valid_if_pending"]
    restrictions_fail = ['p', 'e', 'c', 'n__not_pending_approval_and_not_valid_if_pending', 'n__pending_approval',
                         'n__pending_overdue']

    run_restriction_test(event, order, restrictions_pass, restrictions_fail)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_restrictions_status_approval_pending(event, order):
    order.status = Order.STATUS_PENDING
    order.require_approval = True
    order.valid_if_pending = False
    order.save()
    restrictions_pass = ['n__pending_approval']
    restrictions_fail = ['p', 'e', 'c', 'n__not_pending_approval_and_not_valid_if_pending', "n__valid_if_pending",
                         'n__pending_overdue']

    run_restriction_test(event, order, restrictions_pass, restrictions_fail)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_restrictions_status_overdue_pending(event, order):
    event.settings.payment_term_expire_automatically = False
    order.status = Order.STATUS_PENDING
    order.require_approval = False
    order.valid_if_pending = False
    order.expires = order.expires - datetime.timedelta(days=15)
    order.save()
    restrictions_pass = ['n__pending_overdue', 'n__not_pending_approval_and_not_valid_if_pending']
    restrictions_fail = ['p', 'e', 'c', 'n__pending_approval', "n__valid_if_pending"]

    run_restriction_test(event, order, restrictions_pass, restrictions_fail)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_restrictions_status_expired(event, order):
    order.status = Order.STATUS_EXPIRED
    order.save()
    restrictions_pass = ['e']
    restrictions_fail = ['p', 'c', 'n__not_pending_approval_and_not_valid_if_pending', 'n__pending_approval',
                         'n__valid_if_pending', 'n__pending_overdue']

    run_restriction_test(event, order, restrictions_pass, restrictions_fail)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_restrictions_status_canceled(event, order):
    order.status = Order.STATUS_CANCELED
    order.save()
    restrictions_pass = ['c']
    restrictions_fail = ['p', 'e', 'n__not_pending_approval_and_not_valid_if_pending', 'n__pending_approval',
                         'n__valid_if_pending', 'n__pending_overdue']

    run_restriction_test(event, order, restrictions_pass, restrictions_fail)


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_send_order_pending(event, order):
    djmail.outbox = []

    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', 'n__not_pending_approval_and_not_valid_if_pending',
                                                    'n__valid_if_pending'],
                                subject='meow', template='meow meow meow')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 1


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_send_order_pending_excluded(event, order):
    djmail.outbox = []

    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', "n__valid_if_pending"],
                                subject='meow', template='meow meow meow')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_send_order_valid_if_pending(event, order):
    order.valid_if_pending = True
    order.status = Order.STATUS_PENDING
    order.save()
    djmail.outbox = []

    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', "n__valid_if_pending"],
                                subject='meow', template='meow meow meow')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 1


@pytest.mark.django_db
@pytest.mark.parametrize('status', [
    Order.STATUS_EXPIRED,
    Order.STATUS_CANCELED,
])
@scopes_disabled()
def test_sendmail_rule_send_order_status(status, event, order):
    djmail.outbox = []

    order.status = status
    order.save()

    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', "n__valid_if_pending"],
                                subject='meow', template='meow meow meow')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_send_order_approval(event, order):
    djmail.outbox = []

    order.require_approval = True
    order.save()

    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', 'n__not_pending_approval_and_not_valid_if_pending',
                                                    'n__valid_if_pending'],
                                subject='meow', template='meow meow meow')

    sendmail_run_rules(None)

    assert len(djmail.outbox) == 0


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_only_send_once(event, order):
    djmail.outbox = []

    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', 'n__not_pending_approval_and_not_valid_if_pending',
                                                    'n__valid_if_pending'],
                                subject='meow', template='meow meow meow')

    sendmail_run_rules(None)
    assert len(djmail.outbox) == 1
    sendmail_run_rules(None)
    assert len(djmail.outbox) == 1


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_only_live(event, order):
    djmail.outbox = []
    event.live = False
    event.save()

    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', 'n__not_pending_approval_and_not_valid_if_pending',
                                                    'n__valid_if_pending'],
                                subject='meow', template='meow meow meow')

    sendmail_run_rules(None)
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_rule_disabled(event, order):
    djmail.outbox = []
    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', 'n__not_pending_approval_and_not_valid_if_pending',
                                                    'n__valid_if_pending'],
                                subject='meow', template='meow meow meow', enabled=False)

    sendmail_run_rules(None)
    assert len(djmail.outbox) == 0


@pytest.mark.django_db
@scopes_disabled()
def test_sendmail_context_localization(event, order, pos):
    order.locale = 'de'
    order.save()
    event.settings.name_scheme = 'salutation_given_family'
    InvoiceAddress.objects.create(
        order=order,
        name_parts={'_scheme': 'salutation_given_family', 'salutation': 'Mr', 'given_name': 'Max', 'family_name': 'Mustermann'}
    )

    djmail.outbox = []
    event.sendmail_rules.create(send_date=dt_now - datetime.timedelta(hours=1),
                                restrict_to_status=['p', 'n__not_pending_approval_and_not_valid_if_pending',
                                                    'n__valid_if_pending'],
                                subject='meow', template='Hallo {name_for_salutation}')

    sendmail_run_rules(None)
    assert "Hallo Herr Mustermann" in djmail.outbox[0].body
