import copy
import uuid
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext as _

from pretix.base.storelogic import IncompleteError
from pretix.base.templatetags.money import money_filter


def payment_is_applicable(event, total, cart_positions, invoice_address, cart_session, request):
    for cartpos in cart_positions:
        if cartpos.requires_approval(invoice_address=invoice_address):
            if 'payments' in cart_session:
                del cart_session['payments']
            return False

    used_providers = {p['provider'] for p in cart_session.get('payments', [])}
    for provider in event.get_payment_providers().values():
        if provider.is_implicit(request) if callable(provider.is_implicit) else provider.is_implicit:
            # TODO: do we need a different is_allowed for storefrontapi?
            if provider.is_allowed(request, total=total):
                cart_session['payments'] = [
                    {
                        'id': str(uuid.uuid4()),
                        'provider': provider.identifier,
                        'multi_use_supported': False,
                        'min_value': None,
                        'max_value': None,
                        'info_data': {},
                    }
                ]
                return False
            elif provider.identifier in used_providers:
                # is_allowed might have changed, e.g. after add-on selection
                cart_session['payments'] = [p for p in cart_session['payments'] if
                                            p['provider'] != provider.identifier]
    return True


def current_selected_payments(event, total, cart_session, total_includes_payment_fees=False, fail=False):
    def _remove_payment(payment_id):
        cart_session['payments'] = [p for p in cart_session['payments'] if p.get('id') != payment_id]

    raw_payments = copy.deepcopy(cart_session.get('payments', []))
    payments = []
    total_remaining = total
    for p in raw_payments:
        # This algorithm of treating min/max values and fees needs to stay in sync between the following
        # places in the code base:
        # - pretix.base.services.cart.get_fees
        # - pretix.base.services.orders._get_fees
        # - pretix.presale.storelogic.payment.current_selected_payments
        if p.get('min_value') and total_remaining < Decimal(p['min_value']):
            _remove_payment(p['id'])
            if fail:
                raise IncompleteError(
                    _('Your selected payment method can only be used for a payment of at least {amount}.').format(
                        amount=money_filter(Decimal(p['min_value']), event.currency)
                    )
                )
            continue

        to_pay = total_remaining
        if p.get('max_value') and to_pay > Decimal(p['max_value']):
            to_pay = min(to_pay, Decimal(p['max_value']))

        pprov = event.get_payment_providers(cached=True).get(p['provider'])
        if not pprov:
            _remove_payment(p['id'])
            continue

        if not total_includes_payment_fees:
            fee = pprov.calculate_fee(to_pay)
            total_remaining += fee
            to_pay += fee
        else:
            fee = Decimal('0.00')

        if p.get('max_value') and to_pay > Decimal(p['max_value']):
            to_pay = min(to_pay, Decimal(p['max_value']))

        p['payment_amount'] = to_pay
        p['provider_name'] = pprov.public_name
        p['pprov'] = pprov
        p['fee'] = fee
        total_remaining -= to_pay
        payments.append(p)
    return payments


def ensure_payment_is_completed(event, total, cart_session, request):
    def _remove_payment(payment_id):
        cart_session['payments'] = [p for p in cart_session['payments'] if p.get('id') != payment_id]

    if not cart_session.get('payments'):
        raise IncompleteError(_('Please select a payment method to proceed.'))

    selected = current_selected_payments(event, total, cart_session, fail=True, total_includes_payment_fees=True)
    if sum(p['payment_amount'] for p in selected) != total:
        raise IncompleteError(_('Please select a payment method to proceed.'))

    if len([p for p in selected if not p['multi_use_supported']]) > 1:
        raise ImproperlyConfigured('Multiple non-multi-use providers in session, should never happen')

    for p in selected:
        # TODO: do we need a different is_allowed for storefrontapi?
        if not p['pprov'] or not p['pprov'].is_enabled or not p['pprov'].is_allowed(request, total=total):
            _remove_payment(p['id'])
            if p['payment_amount']:
                raise IncompleteError(_('Please select a payment method to proceed.'))

        if not p['multi_use_supported'] and not p['pprov'].payment_is_valid_session(request):
            raise IncompleteError(_('The payment information you entered was incomplete.'))


def current_payments_valid(cart_session, amount):
    singleton_payments = [p for p in cart_session.get('payments', []) if not p.get('multi_use_supported')]
    if len(singleton_payments) > 1:
        return False

    matched = Decimal('0.00')
    for p in cart_session.get('payments', []):
        if p.get('min_value') and (amount - matched) < Decimal(p['min_value']):
            continue
        if p.get('max_value') and (amount - matched) > Decimal(p['max_value']):
            matched += Decimal(p['max_value'])
        else:
            matched = Decimal('0.00')

    return matched == Decimal('0.00'), amount - matched
