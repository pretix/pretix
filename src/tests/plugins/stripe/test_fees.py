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
import datetime
import re
from decimal import Decimal

import pytest
from django.db import transaction
from django.utils.timezone import now
from django_scopes import scope, scopes_disabled

from pretix.base.models import (
    CartPosition, Event, Item, ItemCategory, Order, OrderFee, OrderPosition,
    Organizer, Quota,
)
from pretix.base.services.orders import change_payment_provider
from pretix.plugins.stripe.payment import (
    STRIPE_METHOD_FEE_STEMS, StripeCC, StripeKlarna, StripePrzelewy24,
    StripeSettingsHolder, StripeWeChatPay,
)
from pretix.testutils.sessions import add_cart_session, get_cart_session_key


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now(),
        plugins='pretix.plugins.stripe',
    )
    with scope(organizer=o):
        yield event


def _set_baseline(event, abs='0.30', percent='2.90', reverse=False):
    event.settings.set('payment_stripe__fee_abs', Decimal(abs))
    event.settings.set('payment_stripe__fee_percent', Decimal(percent))
    event.settings.set('payment_stripe__fee_reverse_calc', reverse)


def _prefix(event):
    return StripeSettingsHolder(event).settings.get_prefix()


def _cleaned(event, *, enabled=None, methods=None, fees=None):
    """Build a cleaned_data dict for settings_form_clean."""
    prefix = _prefix(event)
    data = {prefix + '_enabled': True}
    for stem in STRIPE_METHOD_FEE_STEMS:
        data[prefix + 'method_' + stem] = False
        data[prefix + 'method_%s_fee_custom' % stem] = False
        data[prefix + 'method_%s_fee_abs' % stem] = None
        data[prefix + 'method_%s_fee_percent' % stem] = None
    if enabled:
        for stem in enabled:
            data[prefix + 'method_' + stem] = True
    if methods:
        data.update(methods)
    if fees:
        for stem, values in fees.items():
            if 'custom' in values:
                data[prefix + 'method_%s_fee_custom' % stem] = values['custom']
            if 'abs' in values:
                data[prefix + 'method_%s_fee_abs' % stem] = values['abs']
            if 'percent' in values:
                data[prefix + 'method_%s_fee_percent' % stem] = values['percent']
    return data


def _apply_clean(event, cleaned):
    cleaned = StripeSettingsHolder(event).settings_form_clean(cleaned)
    for key, value in cleaned.items():
        if value is None:
            try:
                del event.settings[key]
            except KeyError:
                pass
        else:
            event.settings.set(key, value)
    return cleaned


# --- calculate_fee ---

@pytest.mark.django_db
def test_baseline_shared_forward(event):
    _set_baseline(event)
    assert StripeCC(event).calculate_fee(Decimal('100.00')) == Decimal('3.20')
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('3.20')


@pytest.mark.django_db
def test_baseline_shared_reverse(event):
    _set_baseline(event, reverse=True)
    assert StripeCC(event).calculate_fee(Decimal('100.00')) == Decimal('3.30')
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('3.30')


@pytest.mark.django_db
def test_card_stem_override(event):
    _set_baseline(event)
    event.settings.set('payment_stripe_method_card_fee_percent', Decimal('10.00'))
    assert StripeCC(event).method_config_key == 'card'
    assert StripeCC(event).calculate_fee(Decimal('100.00')) == Decimal('10.30')
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('3.20')


@pytest.mark.django_db
def test_klarna_percent_override_inherits_abs(event):
    _set_baseline(event)
    event.settings.set('payment_stripe_method_klarna_fee_percent', Decimal('5.00'))
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('5.30')
    assert StripeCC(event).calculate_fee(Decimal('100.00')) == Decimal('3.20')


@pytest.mark.django_db
def test_klarna_abs_override_inherits_percent(event):
    _set_baseline(event)
    event.settings.set('payment_stripe_method_klarna_fee_abs', Decimal('1.50'))
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('4.40')


@pytest.mark.django_db
def test_explicit_zero_abs_override(event):
    _set_baseline(event)
    event.settings.set('payment_stripe_method_klarna_fee_abs', Decimal('0.00'))
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('2.90')


@pytest.mark.django_db
def test_explicit_zero_percent_override(event):
    _set_baseline(event)
    event.settings.set('payment_stripe_method_klarna_fee_percent', Decimal('0.00'))
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('0.30')


@pytest.mark.django_db
def test_reverse_with_percent_only_override(event):
    _set_baseline(event, abs='0.30', percent='2.90', reverse=True)
    event.settings.set('payment_stripe_method_klarna_fee_percent', Decimal('5.00'))
    # reverse: (100 + 0.30) / (1 - 0.05) - 100 = 100.30/0.95 - 100 = 5.578... → 5.58
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('5.58')
    assert StripeCC(event).calculate_fee(Decimal('100.00')) == Decimal('3.30')


@pytest.mark.django_db
def test_reverse_with_abs_only_override(event):
    _set_baseline(event, abs='0.30', percent='2.90', reverse=True)
    event.settings.set('payment_stripe_method_klarna_fee_abs', Decimal('1.00'))
    # reverse: (100 + 1) / (1 - 0.029) - 100 = 101/0.971 - 100 ≈ 4.02
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('4.02')


@pytest.mark.django_db
def test_both_overrides_with_baseline_reverse(event):
    _set_baseline(event, abs='0.30', percent='2.90', reverse=False)
    event.settings.set('payment_stripe_method_klarna_fee_abs', Decimal('1.00'))
    event.settings.set('payment_stripe_method_klarna_fee_percent', Decimal('10.00'))
    event.settings.set('payment_stripe__fee_reverse_calc', True)
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('12.22')


@pytest.mark.django_db
def test_stem_przelewy24_and_wechatpay(event):
    _set_baseline(event, abs='0.00', percent='1.00', reverse=False)
    event.settings.set('payment_stripe_method_przelewy24_fee_percent', Decimal('3.00'))
    event.settings.set('payment_stripe_method_wechatpay_fee_percent', Decimal('4.00'))
    event.settings.set('payment_stripe_method_p24_fee_percent', Decimal('9.00'))
    event.settings.set('payment_stripe_method_wechat_pay_fee_percent', Decimal('9.00'))

    p24 = StripePrzelewy24(event)
    wechat = StripeWeChatPay(event)
    assert p24.method_config_key == 'przelewy24'
    assert wechat.method_config_key == 'wechatpay'
    assert p24.calculate_fee(Decimal('100.00')) == Decimal('3.00')
    assert wechat.calculate_fee(Decimal('100.00')) == Decimal('4.00')


@pytest.mark.django_db
def test_fee_custom_not_read_at_runtime(event):
    """fee_custom is a form latch; calculate_fee only looks at abs/percent keys."""
    _set_baseline(event)
    event.settings.set('payment_stripe_method_klarna_fee_custom', False)
    event.settings.set('payment_stripe_method_klarna_fee_percent', Decimal('5.00'))
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == Decimal('5.30')


# --- settings form ---

@pytest.mark.django_db
def test_form_exposes_fee_fields_for_all_stems(event):
    fields = StripeSettingsHolder(event).settings_form_fields
    keys = list(fields.keys())
    for stem in STRIPE_METHOD_FEE_STEMS:
        assert 'method_%s' % stem in fields
        assert 'method_%s_fee_custom' % stem in fields
        assert 'method_%s_fee_abs' % stem in fields
        assert 'method_%s_fee_percent' % stem in fields
        # Fee fields sit immediately after the method toggle
        i = keys.index('method_%s' % stem)
        assert keys[i + 1] == 'method_%s_fee_custom' % stem
        assert keys[i + 2] == 'method_%s_fee_abs' % stem
        assert keys[i + 3] == 'method_%s_fee_percent' % stem


@pytest.mark.django_db
def test_form_field_wiring(event):
    fields = StripeSettingsHolder(event).settings_form_fields
    custom = fields['method_klarna_fee_custom']
    abs_f = fields['method_klarna_fee_abs']
    pct_f = fields['method_klarna_fee_percent']
    assert custom.widget.attrs['data-display-dependency'] == '#id_payment_stripe_method_klarna'
    assert abs_f.widget.attrs['data-display-dependency'] == '#id_payment_stripe_method_klarna_fee_custom'
    assert pct_f.widget.attrs['data-display-dependency'] == '#id_payment_stripe_method_klarna_fee_custom'
    assert abs_f.widget.attrs['addon_after'] == event.currency
    assert pct_f.widget.attrs['addon_after'] == '%'
    assert 'customized' in str(fields['_fee_abs'].help_text).lower()
    assert 'customized' in str(fields['_fee_percent'].help_text).lower()


@pytest.mark.django_db
@pytest.mark.parametrize('key,value', [
    ('payment_stripe_method_klarna_fee_percent', Decimal('5.00')),
    ('payment_stripe_method_klarna_fee_abs', Decimal('1.00')),
])
def test_fee_custom_initial_from_existing_override(event, key, value):
    event.settings.set(key, value)
    fields = StripeSettingsHolder(event).settings_form_fields
    assert fields['method_klarna_fee_custom'].initial is True
    assert fields['method_card_fee_custom'].initial is False


@pytest.mark.django_db
def test_clean_keeps_overrides_when_customized(event):
    cleaned = _cleaned(
        event,
        enabled=['klarna'],
        fees={'klarna': {'custom': True, 'abs': Decimal('1.00'), 'percent': Decimal('5.00')}},
    )
    cleaned = StripeSettingsHolder(event).settings_form_clean(cleaned)
    prefix = _prefix(event)
    assert cleaned[prefix + 'method_klarna_fee_custom'] is True
    assert cleaned[prefix + 'method_klarna_fee_abs'] == Decimal('1.00')
    assert cleaned[prefix + 'method_klarna_fee_percent'] == Decimal('5.00')


@pytest.mark.django_db
def test_clean_clears_when_method_disabled(event):
    cleaned = _cleaned(
        event,
        enabled=['card'],
        fees={
            'klarna': {'custom': True, 'abs': Decimal('1.00'), 'percent': Decimal('5.00')},
            'card': {'custom': True, 'percent': Decimal('2.00')},
        },
    )
    # klarna method off (default in helper)
    cleaned = StripeSettingsHolder(event).settings_form_clean(cleaned)
    prefix = _prefix(event)
    assert cleaned[prefix + 'method_klarna_fee_custom'] is None
    assert cleaned[prefix + 'method_klarna_fee_abs'] is None
    assert cleaned[prefix + 'method_klarna_fee_percent'] is None
    assert cleaned[prefix + 'method_card_fee_custom'] is True
    assert cleaned[prefix + 'method_card_fee_percent'] == Decimal('2.00')


@pytest.mark.django_db
def test_clean_clears_when_custom_unchecked(event):
    cleaned = _cleaned(
        event,
        enabled=['klarna'],
        fees={'klarna': {'custom': False, 'abs': Decimal('1.00'), 'percent': Decimal('5.00')}},
    )
    cleaned = StripeSettingsHolder(event).settings_form_clean(cleaned)
    prefix = _prefix(event)
    assert cleaned[prefix + 'method_klarna_fee_custom'] is None
    assert cleaned[prefix + 'method_klarna_fee_abs'] is None
    assert cleaned[prefix + 'method_klarna_fee_percent'] is None


@pytest.mark.django_db
def test_clean_clears_empty_customization(event):
    cleaned = _cleaned(
        event,
        enabled=['klarna'],
        fees={'klarna': {'custom': True, 'abs': None, 'percent': None}},
    )
    cleaned = StripeSettingsHolder(event).settings_form_clean(cleaned)
    prefix = _prefix(event)
    assert cleaned[prefix + 'method_klarna_fee_custom'] is None
    assert cleaned[prefix + 'method_klarna_fee_abs'] is None
    assert cleaned[prefix + 'method_klarna_fee_percent'] is None


@pytest.mark.django_db
def test_disabling_method_deletes_stored_overrides(event):
    event.settings.set('payment_stripe_method_klarna', True)
    event.settings.set('payment_stripe_method_klarna_fee_custom', True)
    event.settings.set('payment_stripe_method_klarna_fee_percent', Decimal('5.00'))
    event.settings.set('payment_stripe_method_klarna_fee_abs', Decimal('1.00'))

    cleaned = _cleaned(
        event,
        enabled=['card'],
        fees={'klarna': {'custom': True, 'abs': Decimal('1.00'), 'percent': Decimal('5.00')}},
    )
    _apply_clean(event, cleaned)

    assert event.settings.get('payment_stripe_method_klarna_fee_abs', as_type=Decimal) is None
    assert event.settings.get('payment_stripe_method_klarna_fee_percent', as_type=Decimal) is None
    assert event.settings.get('payment_stripe_method_klarna_fee_custom', as_type=bool) is None
    assert StripeKlarna(event).calculate_fee(Decimal('100.00')) == StripeCC(event).calculate_fee(Decimal('100.00'))


# --- checkout / payment change ---

@pytest.mark.django_db
def test_checkout_shows_different_fees_per_method(client, monkeypatch):
    class MockedAppleDomain:
        livemode = True

    monkeypatch.setattr("stripe.ApplePayDomain.create", lambda **kwargs: MockedAppleDomain())

    orga = Organizer.objects.create(name='CCC', slug='ccc')
    event = Event.objects.create(
        organizer=orga, name='30C3', slug='30c3',
        date_from=datetime.datetime(now().year + 1, 12, 26, tzinfo=datetime.timezone.utc),
        plugins='pretix.plugins.stripe',
        live=True,
    )
    category = ItemCategory.objects.create(event=event, name="Everything", position=0)
    quota = Quota.objects.create(event=event, name='Tickets', size=5)
    ticket = Item.objects.create(
        event=event, name='Early-bird ticket', category=category, default_price=23, admission=True,
    )
    quota.items.add(ticket)
    event.settings.set('attendee_names_asked', False)
    event.settings.set('payment_stripe__enabled', True)
    event.settings.set('payment_stripe_method_card', True)
    event.settings.set('payment_stripe_method_klarna', True)
    event.settings.set('payment_stripe_publishable_key', 'pk_test_dummy')
    event.settings.set('payment_stripe_secret_key', 'sk_test_dummy')
    event.settings.set('payment_stripe_merchant_country', 'DE')
    _set_baseline(event, abs='1.00', percent='2.00', reverse=False)
    event.settings.set('payment_stripe_method_klarna_fee_percent', Decimal('5.00'))

    add_cart_session(client, event, {'email': 'admin@localhost'})
    CartPosition.objects.create(
        event=event, cart_id=get_cart_session_key(client, event), item=ticket,
        price=23, expires=now() + datetime.timedelta(minutes=10),
    )
    client.post('/%s/%s/checkout/questions/' % (event.organizer.slug, event.slug), {
        'email': 'admin@localhost',
    }, follow=True)
    response = client.get('/%s/%s/checkout/payment/' % (event.organizer.slug, event.slug), follow=True)
    content = response.rendered_content

    # card: 23*2%+1 = 1.46; klarna: 23*5%+1 = 2.15 — fee sits in the same panel heading as the radio
    assert 'value="stripe"' in content
    assert 'value="stripe_klarna"' in content
    for provider, amount in (('stripe', '€1.46'), ('stripe_klarna', '€2.15')):
        panel = re.search(
            r'<fieldset[^>]*>.*?value="%s".*?</fieldset>' % re.escape(provider),
            content,
            re.DOTALL,
        )
        assert panel, 'missing payment panel for %s' % provider
        assert amount in panel.group(0)


@pytest.mark.django_db
def test_change_payment_provider_applies_and_reverts_override(event):
    with scopes_disabled():
        ticket = Item.objects.create(event=event, name='Ticket', default_price=23, admission=True)
        order = Order.objects.create(
            code='FOOBAR', event=event, email='dummy@dummy.test',
            status=Order.STATUS_PENDING,
            datetime=now(), expires=now() + datetime.timedelta(days=10),
            total=Decimal('23.00'),
            sales_channel=event.organizer.sales_channels.get(identifier="web"),
        )
        OrderPosition.objects.create(
            order=order, item=ticket, variation=None, price=Decimal('23.00'),
            attendee_name_parts={}, positionid=1,
        )

    _set_baseline(event, abs='1.00', percent='2.00', reverse=False)
    event.settings.set('payment_stripe__enabled', True)
    event.settings.set('payment_stripe_method_klarna', True)
    event.settings.set('payment_stripe_method_card', True)
    event.settings.set('payment_stripe_method_klarna_fee_percent', Decimal('5.00'))

    with scope(organizer=event.organizer):
        with transaction.atomic():
            change_payment_provider(order, StripeKlarna(event))
        order.refresh_from_db()
        with scopes_disabled():
            fee = order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
            assert fee.value == Decimal('2.15')
            assert fee.internal_type == 'stripe_klarna'
            assert order.total == Decimal('25.15')

        with transaction.atomic():
            change_payment_provider(order, StripeCC(event))
        order.refresh_from_db()
        with scopes_disabled():
            fee = order.fees.get(fee_type=OrderFee.FEE_TYPE_PAYMENT)
            assert fee.value == Decimal('1.46')
            assert fee.internal_type == 'stripe'
            assert order.total == Decimal('24.46')
