"""Reset and verify the synthetic Orders fixtures for the Windows SQE app."""

import argparse
import json
import os
import secrets
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import django
from django.core.management import call_command
from django.db import connection, transaction
from django.test import Client
from django.utils.timezone import now
from django_scopes import scopes_disabled

from sqe.windows_settings import BASE_URL, DATA, DATABASE

ORGANIZER = 'sqe-orders'
EVENT = 'orders'
TOTAL = Decimal('20.00')
CONFIG = DATA / 'fixtures.json'

# Use a different order for each mutating browser flow and for fixture verification.
ORDERS = {
    'pay_pending': ('PAY01', 'n'),
    'pay_prior_date': ('PAY02', 'n'),
    'pay_expired': ('PAY03', 'e'),
    'pay_precision': ('PAY04', 'n'),
    'pay_quota_blocked': ('PAY05', 'e'),
    'cancel_paid': ('CAN01', 'p'),
    'cancel_pending': ('CAN02', 'n'),
    'cancel_expired': ('CAN03', 'e'),
    'cancel_viewer': ('CAN04', 'p'),
    'cancel_canceled': ('CAN05', 'c'),
    'positionless': ('SQE01', 'n'),
    'journey': ('SQE02', 'n'),
    'retained_fee': ('SQE03', 'p'),
    'quota_holder': ('SQE04', 'p'),
    # Member 3 fixtures (M3 prefix): UC-05, UC-06, access matrix, accessibility scans, performance.
    'm3_partial': ('M3P01', 'n'),
    'm3_reuse': ('M3P02', 'n'),
    'm3_overpay': ('M3P03', 'n'),
    'm3_bad_date': ('M3P04', 'n'),
    'm3_canceled': ('M3P05', 'c'),
    'm3_neg_amount': ('M3P06', 'n'),
    'm3_kbd_paid': ('M3K01', 'p'),
    'm3_zero_fee': ('M3K02', 'n'),
    'm3_abandon': ('M3K03', 'p'),
    'm3_fee_fix': ('M3K04', 'p'),
    'm3_neg_fee': ('M3K05', 'p'),
    'm3_sec_pay': ('M3S01', 'n'),
    'm3_sec_cancel': ('M3S02', 'p'),
    'm3_sec_api_pay': ('M3S03', 'n'),
    'm3_sec_api_cancel': ('M3S04', 'p'),
    'm3_sec_mgr_pay': ('M3S05', 'n'),
    'm3_sec_mgr_cancel': ('M3S06', 'p'),
    'm3_lh_pending': ('M3L01', 'n'),
    'm3_lh_paid': ('M3L02', 'p'),
    'm3_perf': ('M3R01', 'p'),
}

# Orders seeded with an unconfirmed manual payment that the payment form can reuse (UC-05 alt 1).
CREATED_PAYMENT = {'m3_reuse'}


def fixture_config():
    if CONFIG.is_file():
        config = json.loads(CONFIG.read_text(encoding='utf-8'))
        # Keep existing credentials, but publish aliases added after the file was first written.
        wanted = {alias: code for alias, (code, _) in ORDERS.items()}
        if config.get('orders') != wanted:
            config['orders'] = wanted
            scratch = CONFIG.with_suffix('.tmp')
            scratch.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
            scratch.replace(CONFIG)
        return config

    config = {
        'roles': {
            role: {
                'email': f'{role}@sqe.example.test',
                'password': secrets.token_urlsafe(24),
                'token': secrets.token_hex(32),
            }
            for role in ('manager', 'viewer')
        },
    }
    config.update(baseUrl=BASE_URL, organizer=ORGANIZER, event=EVENT)
    config['orders'] = {alias: code for alias, (code, _) in ORDERS.items()}
    config['priorPaymentDate'] = (now().date() - timedelta(days=1)).isoformat()
    scratch = CONFIG.with_suffix('.tmp')
    scratch.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    scratch.replace(CONFIG)
    return config


def seed(config):
    from pretix.base.models import Event, Item, Order, OrderPayment, OrderPosition, Organizer, Quota, Team, User

    with scopes_disabled(), transaction.atomic():
        timestamp = now()
        organizer = Organizer.objects.create(slug=ORGANIZER, name='SQE Orders')
        event = Event.objects.create(
            organizer=organizer, slug=EVENT, name='SQE Orders Workshop', currency='EUR',
            date_from=timestamp + timedelta(days=30),
        )
        event.settings.set('timezone', 'UTC')
        event.settings.set('locales', ['en'])
        event.settings.set('payment_term_accept_late', True)
        event.settings.set('invoice_generate', 'False')
        sales_channel = organizer.sales_channels.get(identifier='web')
        ticket = Item.objects.create(event=event, name='Workshop ticket', default_price=TOTAL, admission=True)
        scarce_ticket = Item.objects.create(event=event, name='Limited ticket', default_price=TOTAL, admission=True)
        Quota.objects.create(event=event, name='Workshop seats', size=50).items.add(ticket)
        Quota.objects.create(event=event, name='Limited seats', size=1).items.add(scarce_ticket)

        for role, credentials in config['roles'].items():
            permissions = {'event.orders:read': True}
            if role == 'manager':
                permissions['event.orders:write'] = True
            user = User.objects.create_user(credentials['email'], credentials['password'], locale='en', timezone='UTC')
            team = Team.objects.create(organizer=organizer, name=role, limit_event_permissions=permissions)
            team.limit_events.add(event)
            team.members.add(user)
            team.tokens.create(name=f'SQE {role}', token=credentials['token'])

        for alias, (code, status) in ORDERS.items():
            order = Order.objects.create(
                event=event, code=code, email=f'{alias}@sqe.example.test',
                total=TOTAL, status=status, locale='en', sales_channel=sales_channel,
                expires=timestamp + timedelta(days=-2 if status == Order.STATUS_EXPIRED else 7),
                cancellation_date=timestamp if status == Order.STATUS_CANCELED else None,
            )
            if alias != 'positionless':
                item = scarce_ticket if alias in ('pay_quota_blocked', 'quota_holder') else ticket
                OrderPosition.objects.create(order=order, item=item, price=TOTAL)
            if status == Order.STATUS_PAID:
                order.payments.create(
                    provider='manual', amount=TOTAL, state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                    payment_date=timestamp,
                )
            if alias in CREATED_PAYMENT:
                order.payments.create(provider='manual', amount=TOTAL, state=OrderPayment.PAYMENT_STATE_CREATED)
            order.create_transactions()


def reset():
    if connection.vendor != 'sqlite' or Path(connection.settings_dict['NAME']) != DATABASE:
        raise RuntimeError('Reset requires the dedicated SQE SQLite database.')
    config = fixture_config()
    with TemporaryDirectory(prefix='reset-', dir=DATA) as staging:
        candidate = Path(staging) / DATABASE.name
        connection.close()
        connection.settings_dict['NAME'] = str(candidate)
        try:
            call_command('migrate', interactive=False, verbosity=0)
            seed(config)
        finally:
            connection.close()
            connection.settings_dict['NAME'] = str(DATABASE)
        os.replace(candidate, DATABASE)
    print(f'Reset {ORGANIZER}/{EVENT} with {len(ORDERS)} synthetic orders and two scoped roles.')


def verify():
    from pretix.base.models import Order, OrderPayment

    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    with scopes_disabled():
        orders = Order.objects.filter(event__organizer__slug=ORGANIZER, event__slug=EVENT)
        actual = {
            order.code: (order.status, order.total, order.positions.count(),
                         order.payments.filter(state=OrderPayment.PAYMENT_STATE_CONFIRMED).count())
            for order in orders
        }
    expected = {
        code: (status, TOTAL, int(alias != 'positionless'), int(status == 'p'))
        for alias, (code, status) in ORDERS.items()
    }
    if actual != expected:
        raise RuntimeError('Seeded orders differ from the fixture contract. Run reset before verification.')
    print(f'Fixture snapshot matches all {len(actual)} expected orders.')

    host = BASE_URL.split('://', 1)[1]
    endpoint = f'/api/v1/organizers/{ORGANIZER}/events/{EVENT}/orders/{config["orders"]["journey"]}/'
    anonymous = Client(HTTP_HOST=host)
    viewer = Client(HTTP_HOST=host, HTTP_AUTHORIZATION=f'Token {config["roles"]["viewer"]["token"]}')
    manager = Client(HTTP_HOST=host, HTTP_AUTHORIZATION=f'Token {config["roles"]["manager"]["token"]}')
    denied = anonymous.get(endpoint)
    pending = viewer.get(endpoint)
    if denied.status_code != 401 or pending.status_code != 200 or pending.json()['status'] != 'n':
        raise RuntimeError(f'Order read check failed. Anonymous {denied.status_code}, viewer {pending.status_code}.')
    email = config['roles']['manager']['email']
    if not anonymous.login(email=email, password=config['roles']['manager']['password']):
        raise RuntimeError('Could not log in with the seeded manager.')
    control = anonymous.get(f'/control/event/{ORGANIZER}/{EVENT}/orders/')
    if control.status_code != 200 or config['orders']['journey'] not in control.content.decode():
        raise RuntimeError(f'Control order list did not show the seeded journey. HTTP {control.status_code}.')
    print('Control manager login and order list passed. API anonymous 401 and scoped viewer 200.')

    paid = manager.post(endpoint + 'mark_paid/', {'send_email': False}, content_type='application/json')
    if paid.status_code != 200:
        raise RuntimeError(f'W1 returned HTTP {paid.status_code}.')
    after_payment = viewer.get(endpoint).json()
    payments = after_payment['payments']
    if after_payment['status'] != 'p' or len(payments) != 1 or payments[0]['state'] != 'confirmed':
        raise RuntimeError('W1 did not leave exactly one confirmed payment.')
    if Decimal(payments[0]['amount']) != TOTAL:
        raise RuntimeError('W1 confirmed payment did not match the order total.')

    canceled = manager.post(endpoint + 'mark_canceled/', {'send_email': False}, content_type='application/json')
    if canceled.status_code != 200:
        raise RuntimeError(f'W2 returned HTTP {canceled.status_code}.')
    after_cancel = viewer.get(endpoint).json()
    if (after_cancel['code'] != after_payment['code'] or after_cancel['status'] != 'c'
            or not after_cancel['cancellation_date'] or after_cancel['fees'] or after_cancel['payments'] != payments):
        raise RuntimeError('W2 did not cancel the same order with the original payment and zero fees.')
    print(f'{after_cancel["code"]}: pending -> paid (one confirmed EUR 20.00 payment) -> canceled (zero fees).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('reset', 'verify'))
    args = parser.parse_args()
    os.environ['DJANGO_SETTINGS_MODULE'] = 'sqe.windows_settings'
    django.setup()
    {'reset': reset, 'verify': verify}[args.action]()
