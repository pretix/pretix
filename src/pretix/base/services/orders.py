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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Daniel, Flavia Bastos, Heok Hong Low, Jakob Schnell,
# Sanket Dasgupta, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import logging
import operator
import sys
from collections import Counter, defaultdict, namedtuple
from datetime import datetime, time, timedelta
from decimal import Decimal
from functools import reduce
from time import sleep
from typing import List, Optional

from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import (
    Count, Exists, F, IntegerField, Max, Min, OuterRef, Q, QuerySet, Sum,
    Value,
)
from django.db.models.functions import Coalesce, Greatest
from django.db.transaction import get_connection
from django.dispatch import receiver
from django.utils.functional import cached_property
from django.utils.timezone import make_aware, now
from django.utils.translation import gettext as _, gettext_lazy, ngettext_lazy
from django_scopes import scopes_disabled

from pretix.api.models import OAuthApplication
from pretix.base.decimal import round_decimal
from pretix.base.email import get_email_context
from pretix.base.i18n import get_language_without_region, language
from pretix.base.media import MEDIA_TYPES
from pretix.base.models import (
    CartPosition, Device, Event, GiftCard, Item, ItemVariation, Membership,
    Order, OrderPayment, OrderPosition, Quota, Seat, SeatCategoryMapping, User,
    Voucher,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.orders import (
    BlockedTicketSecret, InvoiceAddress, OrderFee, OrderRefund,
    generate_secret,
)
from pretix.base.models.organizer import SalesChannel, TeamAPIToken
from pretix.base.models.tax import TAXED_ZERO, TaxedPrice, TaxRule
from pretix.base.payment import GiftCardPayment, PaymentException
from pretix.base.reldate import RelativeDateWrapper
from pretix.base.secrets import assign_ticket_secret
from pretix.base.services import cart, tickets
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_qualified,
    invoice_transmission_separately, order_invoice_transmission_separately,
    transmit_invoice,
)
from pretix.base.services.locking import (
    LOCK_TRUST_WINDOW, LockTimeoutException, lock_objects,
)
from pretix.base.services.memberships import (
    create_membership, validate_memberships_in_order,
)
from pretix.base.services.pricing import (
    apply_discounts, apply_rounding, get_listed_price, get_price,
)
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.services.tasks import ProfiledEventTask, ProfiledTask
from pretix.base.services.tax import split_fee_for_taxes
from pretix.base.signals import (
    order_approved, order_canceled, order_changed, order_denied, order_expired,
    order_expiry_changed, order_fee_calculation, order_paid, order_placed,
    order_reactivated, order_split, order_valid_if_pending, periodic_task,
    validate_order,
)
from pretix.base.timemachine import time_machine_now, time_machine_now_assigned
from pretix.celery_app import app
from pretix.helpers import OF_SELF
from pretix.helpers.models import modelcopy
from pretix.helpers.periodic import minimum_interval
from pretix.testutils.middleware import debugflags_var


class OrderError(Exception):
    def __init__(self, *args):
        msg = args[0]
        msgargs = args[1] if len(args) > 1 else None
        self.args = args
        if msgargs:
            msg = _(msg) % msgargs
        else:
            # force msg to string to make sure lazy-translation is done in current locale-context
            # otherwise translation might happen in celery-context, which uses default-locale
            # also translate with _/gettext to keep it backwards compatible
            msg = _(str(msg))
        super().__init__(msg)


error_messages = {
    'positions_removed': gettext_lazy(
        'Some products can no longer be purchased and have been removed from your cart for the following reason: %s'
    ),
    'unavailable': gettext_lazy(
        'Some of the products you selected were no longer available. '
        'Please see below for details.'
    ),
    'in_part': gettext_lazy(
        'Some of the products you selected were no longer available in '
        'the quantity you selected. Please see below for details.'
    ),
    'price_changed': gettext_lazy(
        'The price of some of the items in your cart has changed in the '
        'meantime. Please see below for details.'
    ),
    'internal': gettext_lazy("An internal error occurred, please try again."),
    'race_condition': gettext_lazy("This order was changed by someone else simultaneously. Please check if your "
                                   "changes are still accurate and try again."),
    'empty': gettext_lazy("Your cart is empty."),
    'max_items': ngettext_lazy(
        "You cannot select more than %s item per order.",
        "You cannot select more than %s items per order."
    ),
    'max_items_per_product': ngettext_lazy(
        "You cannot select more than %(max)s item of the product %(product)s. We removed the surplus items from your cart.",
        "You cannot select more than %(max)s items of the product %(product)s. We removed the surplus items from your cart.",
        "max"
    ),
    'busy': gettext_lazy(
        'We were not able to process your request completely as the '
        'server was too busy. Please try again.'
    ),
    'not_started': gettext_lazy('The booking period for this event has not yet started.'),
    'ended': gettext_lazy('The booking period has ended.'),
    'voucher_min_usages': ngettext_lazy(
        'The voucher code "%(voucher)s" can only be used if you select at least %(number)s matching products.',
        'The voucher code "%(voucher)s" can only be used if you select at least %(number)s matching products.',
        'number'
    ),
    'voucher_invalid': gettext_lazy('The voucher code used for one of the items in your cart is not known in our database.'),
    'voucher_redeemed': gettext_lazy(
        'The voucher code used for one of the items in your cart has already been used the maximum '
        'number of times allowed. We removed this item from your cart.'
    ),
    'voucher_budget_used': gettext_lazy(
        'The voucher code used for one of the items in your cart has already been too often. We '
        'adjusted the price of the item in your cart.'
    ),
    'voucher_expired': gettext_lazy(
        'The voucher code used for one of the items in your cart is expired. We removed this item from your cart.'
    ),
    'voucher_invalid_item': gettext_lazy(
        'The voucher code used for one of the items in your cart is not valid for this item. We removed this item from your cart.'
    ),
    'voucher_required': gettext_lazy('You need a valid voucher code to order one of the products.'),
    'seat_invalid': gettext_lazy('One of the seats in your order was invalid, we removed the position from your cart.'),
    'seat_unavailable': gettext_lazy('One of the seats in your order has been taken in the meantime, we removed the position from your cart.'),
    'country_blocked': gettext_lazy('One of the selected products is not available in the selected country.'),
    'not_for_sale': gettext_lazy('You selected a product which is not available for sale.'),
    'addon_invalid_base': gettext_lazy('You can not select an add-on for the selected product.'),
    'addon_duplicate_item': gettext_lazy('You can not select two variations of the same add-on product.'),
    'addon_max_count': ngettext_lazy(
        'You can select at most %(max)s add-on from the category %(cat)s for the product %(base)s.',
        'You can select at most %(max)s add-ons from the category %(cat)s for the product %(base)s.',
        'max'
    ),
    'addon_min_count': ngettext_lazy(
        'You need to select at least %(min)s add-on from the category %(cat)s for the product %(base)s.',
        'You need to select at least %(min)s add-ons from the category %(cat)s for the product %(base)s.',
        'min'
    ),
    'addon_no_multi': gettext_lazy('You can select every add-on from the category %(cat)s for the product %(base)s at most once.'),
    'addon_already_checked_in': gettext_lazy('You cannot remove the position %(addon)s since it has already been checked in.'),
    'currency_XXX': gettext_lazy('Paid products not supported without a valid currency.'),
}

logger = logging.getLogger(__name__)


def mark_order_paid(*args, **kwargs):
    raise NotImplementedError("This method is no longer supported since pretix 1.17.")


def reactivate_order(order: Order, force: bool=False, user: User=None, auth=None):
    """
    Reactivates a canceled order. If ``force`` is not set to ``True``, this will fail if there is not
    enough quota.
    """
    if order.status != Order.STATUS_CANCELED:
        raise OrderError(_('The order was not canceled.'))

    with transaction.atomic():
        is_available = order._is_still_available(now(), count_waitinglist=False, check_voucher_usage=True,
                                                 check_memberships=True, lock=True, force=force)
        if is_available is True:
            if order.payment_refund_sum >= order.total and not order.require_approval:
                order.status = Order.STATUS_PAID
            else:
                order.status = Order.STATUS_PENDING
            order.cancellation_date = None
            order.set_expires(now(),
                              order.event.subevents.filter(id__in=[p.subevent_id for p in order.positions.all()]))
            order.save(update_fields=['expires', 'status', 'cancellation_date'])
            order.log_action(
                'pretix.event.order.reactivated',
                user=user,
                auth=auth,
                data={
                    'expires': order.expires,
                }
            )
            for position in order.positions.all():
                if position.voucher:
                    Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') + 1))

                for gc in position.issued_gift_cards.all():
                    gc = GiftCard.objects.select_for_update(of=OF_SELF).get(pk=gc.pk)
                    gc.transactions.create(value=position.price, order=order, acceptor=order.event.organizer)
                    gc.log_action(
                        action='pretix.giftcards.transaction.manual',
                        user=user,
                        auth=auth,
                        data={
                            'value': position.price,
                            'acceptor_id': order.event.organizer.id
                        }
                    )
                    break

                for m in position.granted_memberships.all():
                    m.canceled = False
                    m.save()
            order.create_transactions()
        else:
            raise OrderError(is_available)

    order_reactivated.send(order.event, order=order)
    if order.status == Order.STATUS_PAID:
        order_paid.send(order.event, order=order)

    num_invoices = order.invoices.filter(is_cancellation=False).count()
    if num_invoices > 0 and order.invoices.filter(is_cancellation=True).count() >= num_invoices and invoice_qualified(order):
        try:
            generate_invoice(order)
        except Exception as e:
            logger.exception("Could not generate invoice.")
            order.log_action("pretix.event.order.invoice.failed", data={
                "exception": str(e)
            })


def extend_order(order: Order, new_date: datetime, force: bool=False, valid_if_pending: bool=None, user: User=None, auth=None):
    """
    Extends the deadline of an order. If the order is already expired, the quota will be checked to
    see if this is actually still possible. If ``force`` is set to ``True``, the result of this check
    will be ignored.
    """
    if new_date < now():
        raise OrderError(_('The new expiry date needs to be in the future.'))

    def change(was_expired=True):
        old_date = order.expires
        order.expires = new_date
        if was_expired:
            order.status = Order.STATUS_PENDING
        if valid_if_pending is not None and valid_if_pending != order.valid_if_pending:
            order.valid_if_pending = valid_if_pending
            if valid_if_pending:
                order.log_action(
                    'pretix.event.order.valid_if_pending.set',
                    user=user,
                    auth=auth,
                )
            else:
                order.log_action(
                    'pretix.event.order.valid_if_pending.unset',
                    user=user,
                    auth=auth,
                )
        order.save(update_fields=['valid_if_pending', 'expires'] + (['status'] if was_expired else []))
        if old_date != new_date:
            order.log_action(
                'pretix.event.order.expirychanged',
                user=user,
                auth=auth,
                data={
                    'expires': order.expires,
                    'force': force,
                    'state_change': was_expired
                }
            )
            order_expiry_changed.send(sender=order.event, order=order)

        if was_expired:
            num_invoices = order.invoices.filter(is_cancellation=False).count()
            if num_invoices > 0 and order.invoices.filter(is_cancellation=True).count() >= num_invoices and invoice_qualified(order):
                try:
                    generate_invoice(order)
                except Exception as e:
                    logger.exception("Could not generate invoice.")
                    order.log_action("pretix.event.order.invoice.failed", data={
                        "exception": str(e)
                    })
            order.create_transactions()

    with transaction.atomic():
        if order.status == Order.STATUS_PENDING:
            change(was_expired=False)
        else:
            is_available = order._is_still_available(now(), count_waitinglist=False, lock=True, force=force)
            if is_available is True:
                change(was_expired=True)
            else:
                raise OrderError(is_available)


@transaction.atomic
def mark_order_refunded(order, user=None, auth=None, api_token=None):
    oautha = auth.pk if isinstance(auth, OAuthApplication) else None
    device = auth.pk if isinstance(auth, Device) else None
    api_token = (api_token.pk if api_token else None) or (auth if isinstance(auth, TeamAPIToken) else None)
    return _cancel_order(
        order.pk, user.pk if user else None, send_mail=False, api_token=api_token, device=device, oauth_application=oautha
    )


def mark_order_expired(order, user=None, auth=None):
    """
    Mark this order as expired. This sets the payment status and returns the order object.
    :param order: The order to change
    :param user: The user that performed the change
    """
    with transaction.atomic():
        if isinstance(order, int):
            order = Order.objects.get(pk=order)
        if isinstance(user, int):
            user = User.objects.get(pk=user)
        order.status = Order.STATUS_EXPIRED
        order.save(update_fields=['status'])

        order.log_action('pretix.event.order.expired', user=user, auth=auth)
        i = order.invoices.filter(is_cancellation=False).last()
        if i and not i.refered.exists():
            generate_cancellation(i)
        order.create_transactions()

    order_expired.send(order.event, order=order)
    return order


def approve_order(order, user=None, send_mail: bool=True, auth=None, force=False):
    """
    Mark this order as approved
    :param order: The order to change
    :param user: The user that performed the change
    """
    with transaction.atomic():
        if not order.require_approval or not order.status == Order.STATUS_PENDING:
            raise OrderError(_('This order is not pending approval.'))

        order.require_approval = False
        order.set_expires(now(), order.event.subevents.filter(id__in=[p.subevent_id for p in order.positions.all()]))
        order.save(update_fields=['require_approval', 'expires'])
        order.create_transactions()

        order.log_action('pretix.event.order.approved', user=user, auth=auth)
        if order.total == Decimal('0.00'):
            p = order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CREATED,
                provider='free',
                amount=0,
                fee=None
            )
            try:
                p.confirm(send_mail=False, count_waitinglist=False, user=user, auth=auth, ignore_date=True, force=force)
            except Quota.QuotaExceededException:
                raise OrderError(error_messages['unavailable'])

    order_approved.send(order.event, order=order)

    invoice = order.invoices.last()  # Might be generated by plugin already

    transmit_invoice_task = order_invoice_transmission_separately(order)
    transmit_invoice_mail = not transmit_invoice_task and order.event.settings.invoice_email_attachment and order.email

    if order.event.settings.get('invoice_generate') == 'True' and invoice_qualified(order):
        if not invoice:
            try:
                invoice = generate_invoice(
                    order,
                    # send_mail will trigger PDF generation later
                    trigger_pdf=not transmit_invoice_mail
                )
                if transmit_invoice_task:
                    transmit_invoice.apply_async(args=(order.event_id, invoice.pk, False))
            except Exception as e:
                logger.exception("Could not generate invoice.")
                order.log_action("pretix.event.order.invoice.failed", data={
                    "exception": str(e)
                })

    if send_mail:
        with language(order.locale, order.event.settings.region):
            if order.total == Decimal('0.00'):
                email_template = order.event.settings.mail_text_order_approved_free
                email_subject = order.event.settings.mail_subject_order_approved_free
                email_attendees = order.event.settings.mail_send_order_approved_free_attendee
                email_attendee_template = order.event.settings.mail_text_order_approved_free_attendee
                email_attendee_subject = order.event.settings.mail_subject_order_approved_free_attendee
            else:
                email_template = order.event.settings.mail_text_order_approved
                email_subject = order.event.settings.mail_subject_order_approved
                email_attendees = order.event.settings.mail_send_order_approved_attendee
                email_attendee_template = order.event.settings.mail_text_order_approved_attendee
                email_attendee_subject = order.event.settings.mail_subject_order_approved_attendee

            email_context = get_email_context(event=order.event, order=order)
            order.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.order_approved', user,
                attach_tickets=True,
                attach_ical=order.event.settings.mail_attach_ical and (
                    not order.event.settings.mail_attach_ical_paid_only or
                    order.total == Decimal('0.00') or
                    order.valid_if_pending
                ),
                invoices=[invoice] if invoice and transmit_invoice_mail else []
            )

            if email_attendees:
                for p in order.positions.all():
                    if p.addon_to_id is None and p.attendee_email and p.attendee_email != order.email:
                        email_attendee_context = get_email_context(event=order.event, order=order, position=p)
                        p.send_mail(
                            email_attendee_subject, email_attendee_template, email_attendee_context,
                            'pretix.event.order.email.order_approved', user,
                            attach_tickets=True,
                        )

    return order.pk


def deny_order(order, comment='', user=None, send_mail: bool=True, auth=None):
    """
    Mark this order as canceled
    :param order: The order to change
    :param user: The user that performed the change
    """
    with transaction.atomic():
        if not order.require_approval or not order.status == Order.STATUS_PENDING:
            raise OrderError(_('This order is not pending approval.'))

        order.status = Order.STATUS_CANCELED
        order.save(update_fields=['status'])

        order.log_action('pretix.event.order.denied', user=user, auth=auth, data={
            'comment': comment
        })
        i = order.invoices.filter(is_cancellation=False).last()
        if i:
            generate_cancellation(i)

        for position in order.positions.all():
            if position.voucher:
                Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))
        order.create_transactions()

    order_denied.send(order.event, order=order)

    if send_mail:
        with language(order.locale, order.event.settings.region):
            email_template = order.event.settings.mail_text_order_denied
            email_subject = order.event.settings.mail_subject_order_denied
            email_context = get_email_context(event=order.event, order=order, comment=comment)
            order.send_mail(
                email_subject, email_template, email_context,
                'pretix.event.order.email.order_denied', user
            )

    return order.pk


def _cancel_order(order, user=None, send_mail: bool=True, api_token=None, device=None, oauth_application=None,
                  cancellation_fee=None, keep_fees=None, cancel_invoice=True, comment=None, tax_mode=None):
    """
    Mark this order as canceled
    :param order: The order to change
    :param user: The user that performed the change
    """
    # If new actions are added to this function, make sure to add the reverse operation to reactivate_order()
    with transaction.atomic():
        if isinstance(order, int):
            order = Order.objects.select_for_update(of=OF_SELF).get(pk=order)
        if isinstance(user, int):
            user = User.objects.get(pk=user)
        if isinstance(api_token, int):
            api_token = TeamAPIToken.objects.get(pk=api_token)
        if isinstance(device, int):
            device = Device.objects.get(pk=device)
        if isinstance(oauth_application, int):
            oauth_application = OAuthApplication.objects.get(pk=oauth_application)
        if isinstance(cancellation_fee, str):
            cancellation_fee = Decimal(cancellation_fee)
        elif isinstance(cancellation_fee, (float, int)):
            cancellation_fee = round_decimal(cancellation_fee, order.event.currency)

        tax_mode = tax_mode or order.event.settings.tax_rule_cancellation

        if not order.cancel_allowed():
            raise OrderError(_('You cannot cancel this order.'))
        invoices = []
        if cancel_invoice:
            i = order.invoices.filter(is_cancellation=False).last()
            if i and not i.refered.exists():
                invoices.append(generate_cancellation(i))

        for position in order.positions.all():
            for gc in position.issued_gift_cards.all():
                gc = GiftCard.objects.select_for_update(of=OF_SELF).get(pk=gc.pk)
                if gc.value < position.price:
                    raise OrderError(
                        _('This order can not be canceled since the gift card {card} purchased in '
                          'this order has already been redeemed.').format(
                            card=gc.secret
                        )
                    )
                else:
                    gc.transactions.create(value=-position.price, order=order, acceptor=order.event.organizer)
                    gc.log_action(
                        action='pretix.giftcards.transaction.manual',
                        user=user,
                        data={
                            'value': -position.price,
                            'acceptor_id': order.event.organizer.id,
                        }
                    )

            for m in position.granted_memberships.all():
                m.canceled = True
                m.save()

        if cancellation_fee:
            positions = []
            for position in order.positions.all():
                positions.append(position)
                if position.voucher:
                    Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))
                position.canceled = True
                assign_ticket_secret(
                    event=order.event, position=position, force_invalidate_if_revokation_list_used=True, force_invalidate=False, save=False
                )
                position.save(update_fields=['canceled', 'secret'])
            new_fee = cancellation_fee
            for fee in order.fees.all():
                if keep_fees and fee in keep_fees:
                    new_fee -= fee.value
                else:
                    positions.append(fee)
                    fee.canceled = True
                    fee.save(update_fields=['canceled'])

            if new_fee:
                tax_rule_zero = TaxRule.zero()
                if tax_mode == "default":
                    fee_values = [(order.event.cached_default_tax_rule or tax_rule_zero, new_fee)]
                elif tax_mode == "split":
                    fee_values = split_fee_for_taxes(positions, new_fee, order.event)
                else:
                    fee_values = [(tax_rule_zero, new_fee)]

                try:
                    ia = order.invoice_address
                except InvoiceAddress.DoesNotExist:
                    ia = None

                for tax_rule, price in fee_values:
                    tax_rule = tax_rule or tax_rule_zero
                    tax = tax_rule.tax(
                        price, invoice_address=ia, base_price_is="gross"
                    )
                    f = OrderFee(
                        fee_type=OrderFee.FEE_TYPE_CANCELLATION,
                        value=price,
                        order=order,
                        tax_rate=tax.rate,
                        tax_code=tax.code,
                        tax_value=tax.tax,
                        tax_rule=tax_rule,
                    )
                    f.save()

            if cancellation_fee > order.total:
                raise OrderError(_('The cancellation fee cannot be higher than the total amount of this order.'))
            elif order.payment_refund_sum < cancellation_fee:
                order.status = Order.STATUS_PENDING
                order.set_expires()
            else:
                order.status = Order.STATUS_PAID
            order.total = cancellation_fee
            order.cancellation_date = now()
            order.save(update_fields=['status', 'cancellation_date', 'total'])

            if cancel_invoice and i:
                try:
                    invoices.append(generate_invoice(order))
                except Exception as e:
                    logger.exception("Could not generate invoice.")
                    order.log_action("pretix.event.order.invoice.failed", data={
                        "exception": str(e)
                    })
        else:
            order.status = Order.STATUS_CANCELED
            order.cancellation_date = now()
            order.save(update_fields=['status', 'cancellation_date'])

            for position in order.positions.all():
                assign_ticket_secret(
                    event=order.event, position=position, force_invalidate_if_revokation_list_used=True, force_invalidate=False, save=True
                )
                if position.voucher:
                    Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))

        order.log_action('pretix.event.order.canceled', user=user, auth=api_token or oauth_application or device,
                         data={'cancellation_fee': cancellation_fee, 'comment': comment})
        order.cancellation_requests.all().delete()

        order.create_transactions()

        transmit_invoices_task = [i for i in invoices if invoice_transmission_separately(i)]
        transmit_invoices_mail = [i for i in invoices if i not in transmit_invoices_task and order.event.settings.invoice_email_attachment]
        for i in transmit_invoices_task:
            transmit_invoice.apply_async(args=(order.event_id, i.pk, False))

        if send_mail:
            with language(order.locale, order.event.settings.region):
                email_template = order.event.settings.mail_text_order_canceled
                email_subject = order.event.settings.mail_subject_order_canceled
                email_context = get_email_context(event=order.event, order=order, comment=comment or "")
                order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.order_canceled', user,
                    invoices=transmit_invoices_mail,
                )

    for p in order.payments.filter(state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING)):
        try:
            with transaction.atomic():
                p.payment_provider.cancel_payment(p)
                order.log_action(
                    'pretix.event.order.payment.canceled',
                    {
                        'local_id': p.local_id,
                        'provider': p.provider,
                    },
                    user=user,
                    auth=api_token or oauth_application or device
                )
        except PaymentException as e:
            order.log_action(
                'pretix.event.order.payment.canceled.failed',
                {
                    'local_id': p.local_id,
                    'provider': p.provider,
                    'error': str(e)
                },
                user=user,
                auth=api_token or oauth_application or device
            )

    order_canceled.send(order.event, order=order)
    return order.pk


def _check_date(event: Event, now_dt: datetime):
    if event.presale_start and now_dt < event.presale_start:
        raise OrderError(error_messages['not_started'])
    if event.presale_has_ended:
        raise OrderError(error_messages['ended'])

    if not event.has_subevents:
        tlv = event.settings.get('payment_term_last', as_type=RelativeDateWrapper)
        if tlv:
            term_last = make_aware(datetime.combine(
                tlv.datetime(event).date(),
                time(hour=23, minute=59, second=59)
            ), event.timezone)
            if term_last < now_dt:
                raise OrderError(error_messages['ended'])


def _check_positions(event: Event, now_dt: datetime, time_machine_now_dt: datetime, positions: List[CartPosition],
                     sales_channel: SalesChannel, address: InvoiceAddress=None, customer=None):
    err = None
    _check_date(event, time_machine_now_dt)

    products_seen = Counter()
    q_avail = Counter()
    v_avail = Counter()
    v_usages = Counter()
    v_budget = {}
    deleted_positions = set()
    seats_seen = set()

    def delete(cp):
        # Delete a cart position, including parents and children, if applicable
        if cp.is_bundled:
            delete(cp.addon_to)
        else:
            for p in cp.addons.all():
                deleted_positions.add(p.pk)
                p.delete()
            deleted_positions.add(cp.pk)
            cp.delete()

    sorted_positions = list(sorted(positions, key=lambda c: (-int(c.is_bundled), c.pk)))

    for cp in sorted_positions:
        cp._cached_quotas = list(cp.quotas)

    for cp in sorted_positions:
        try:
            cart._check_position_constraints(
                event=event,
                item=cp.item,
                variation=cp.variation,
                voucher=cp.voucher,
                subevent=cp.subevent,
                seat=cp.seat,
                sales_channel=sales_channel,
                already_in_cart=True,
                cart_is_expired=cp.expires < now_dt,
                real_now_dt=now_dt,
                item_requires_seat=cp.requires_seat,
                is_addon=bool(cp.addon_to_id),
                is_bundled=bool(cp.addon_to_id) and cp.is_bundled,
            )
            # Quota, seat, and voucher availability is checked for below
            # Prices are checked for below
            # Memberships are checked in _create_order
        except cart.CartPositionError as e:
            err = error_messages['positions_removed'] % str(e)
            delete(cp)

    # Create locks
    sorted_positions = [cp for cp in sorted_positions if cp.pk and cp.pk not in deleted_positions]  # eliminate deleted
    if any(cp.expires < now() + timedelta(seconds=LOCK_TRUST_WINDOW) for cp in sorted_positions):
        # No need to perform any locking if the cart positions still guarantee everything long enough.
        full_lock_required = any(
            getattr(o, 'seat', False) for o in sorted_positions
        ) and event.settings.seating_minimal_distance > 0
        if full_lock_required:
            # We lock the entire event in this case since we don't want to deal with fine-granular locking
            # in the case of seating distance enforcement
            lock_objects([event])
        else:
            lock_objects(
                [q for q in reduce(operator.or_, (set(cp._cached_quotas) for cp in sorted_positions), set()) if q.size is not None] +
                [op.voucher for op in sorted_positions if op.voucher] +
                [op.seat for op in sorted_positions if op.seat],
                shared_lock_objects=[event]
            )

    # Check maximum order size
    limit = min(int(event.settings.max_items_per_order), settings.PRETIX_MAX_ORDER_SIZE)
    if sum(1 for cp in sorted_positions if not cp.addon_to) > limit:
        err = err or (error_messages['max_items'] % limit)

    # Check availability
    for i, cp in enumerate(sorted_positions):
        if cp.pk in deleted_positions or not cp.pk:
            continue

        quotas = cp._cached_quotas

        # Product per order limits
        products_seen[cp.item] += 1
        if cp.item.max_per_order and products_seen[cp.item] > cp.item.max_per_order:
            err = error_messages['max_items_per_product'] % {
                'max': cp.item.max_per_order,
                'product': cp.item.name
            }
            delete(cp)
            break

        # Voucher availability
        if cp.voucher:
            v_usages[cp.voucher] += 1
            if cp.voucher not in v_avail:
                cp.voucher.refresh_from_db(fields=['redeemed'])
                redeemed_in_carts = CartPosition.objects.filter(
                    Q(voucher=cp.voucher) & Q(event=event) & Q(expires__gte=now_dt)
                ).exclude(cart_id=cp.cart_id)
                v_avail[cp.voucher] = cp.voucher.max_usages - cp.voucher.redeemed - redeemed_in_carts.count()
            v_avail[cp.voucher] -= 1
            if v_avail[cp.voucher] < 0:
                err = err or error_messages['voucher_redeemed']
                delete(cp)
                continue

        # Check duplicate seats in order
        if cp.seat in seats_seen:
            err = err or error_messages['seat_invalid']
            delete(cp)
            break

        if cp.seat:
            seats_seen.add(cp.seat)
            # Unlike quotas (which we blindly trust as long as the position is not expired), we check seats every
            # time, since we absolutely can not overbook a seat.
            if not cp.seat.is_available(ignore_cart=cp, ignore_voucher_id=cp.voucher_id, sales_channel=sales_channel.identifier):
                err = err or error_messages['seat_unavailable']
                delete(cp)
                continue

        # Check useful quota configuration
        if len(quotas) == 0:
            err = err or error_messages['unavailable']
            delete(cp)
            continue

        quota_ok = True
        ignore_all_quotas = cp.expires >= now_dt or (
            cp.voucher and (
                cp.voucher.allow_ignore_quota or (cp.voucher.block_quota and cp.voucher.quota is None)
            )
        )

        if not ignore_all_quotas:
            for quota in quotas:
                if cp.voucher and cp.voucher.block_quota and cp.voucher.quota_id == quota.pk:
                    continue
                if quota not in q_avail:
                    avail = quota.availability(now_dt)
                    q_avail[quota] = avail[1] if avail[1] is not None else sys.maxsize
                q_avail[quota] -= 1
                if q_avail[quota] < 0:
                    err = err or error_messages['unavailable']
                    quota_ok = False
                    break

        if not quota_ok:
            # Sorry, can't let you keep that!
            delete(cp)

    for voucher, cnt in v_usages.items():
        if 0 < cnt < voucher.min_usages_remaining:
            raise OrderError(error_messages['voucher_min_usages'] % {
                'voucher': voucher.code,
                'number': voucher.min_usages_remaining,
            })

    # Check prices
    sorted_positions = [cp for cp in sorted_positions if cp.pk and cp.pk not in deleted_positions]  # eliminate deleted
    old_total = sum(cp.price for cp in sorted_positions)
    for i, cp in enumerate(sorted_positions):
        if cp.listed_price is None:
            # migration from pre-discount cart positions
            cp.update_listed_price_and_voucher(max_discount=None)
            cp.migrate_free_price_if_necessary()

        # deal with max discount
        max_discount = None
        if cp.voucher and cp.voucher.budget is not None:
            if cp.voucher not in v_budget:
                v_budget[cp.voucher] = cp.voucher.budget - cp.voucher.budget_used()
            max_discount = max(v_budget[cp.voucher], 0)

        if cp.expires < now_dt or cp.listed_price is None:
            # Guarantee on listed price is expired
            cp.update_listed_price_and_voucher(max_discount=max_discount)
        elif cp.voucher:
            cp.update_listed_price_and_voucher(max_discount=max_discount, voucher_only=True)

        if max_discount is not None:
            v_budget[cp.voucher] = v_budget[cp.voucher] - (cp.listed_price - cp.price_after_voucher)

        try:
            cp.update_line_price(address, [b for b in sorted_positions if b.addon_to_id == cp.pk and b.is_bundled and b.pk and b.pk not in deleted_positions])
        except TaxRule.SaleNotAllowed:
            err = err or error_messages['country_blocked']
            delete(cp)
            continue

    sorted_positions = [cp for cp in sorted_positions if cp.pk and cp.pk not in deleted_positions]  # eliminate deleted
    discount_results = apply_discounts(
        event,
        sales_channel.identifier,
        [
            (cp.item_id, cp.subevent_id, cp.subevent.date_from if cp.subevent_id else None, cp.line_price_gross,
             cp.addon_to, cp.is_bundled, cp.listed_price - cp.price_after_voucher)
            for cp in sorted_positions
        ]
    )
    for cp, (new_price, discount) in zip(sorted_positions, discount_results):
        if cp.gross_price_before_rounding != new_price or cp.discount_id != (discount.pk if discount else None):
            cp.price = new_price
            cp.price_includes_rounding_correction = Decimal("0.00")
            cp.discount = discount
            cp.save(update_fields=['price', 'price_includes_rounding_correction', 'discount'])

    # After applying discounts, add-on positions might still have a reference to the *old* version of the
    # parent position, which can screw up ordering later since the system sees inconsistent data.
    by_id = {cp.pk: cp for cp in sorted_positions}
    for cp in sorted_positions:
        if cp.addon_to_id:
            cp.addon_to = by_id[cp.addon_to_id]

    new_total = sum(cp.price for cp in sorted_positions)
    if old_total != new_total:
        err = err or error_messages['price_changed']

    # Store updated positions
    for cp in sorted_positions:
        cp.expires = now_dt + timedelta(
            minutes=event.settings.get('reservation_time', as_type=int))
        cp.save(update_fields=['expires'])

    if err:
        raise OrderError(err)


def _apply_rounding_and_fees(positions: List[CartPosition], payment_requests: List[dict], address: InvoiceAddress,
                             meta_info: dict, event: Event, require_approval=False):
    fees = []
    # Pre-rounding, pre-fee total is used for fee calculation
    total = sum([c.gross_price_before_rounding for c in positions])

    gift_cards = []  # for backwards compatibility
    for p in payment_requests:
        if p['provider'] == 'giftcard':
            gift_cards.append(GiftCard.objects.get(pk=p['info_data']['gift_card']))

    for recv, resp in order_fee_calculation.send(sender=event, invoice_address=address, total=total, payment_requests=payment_requests,
                                                 meta_info=meta_info, positions=positions, gift_cards=gift_cards):
        if resp:
            fees += resp

    for fee in fees:
        fee._calculate_tax(invoice_address=address, event=event)
        if fee.tax_rule and not fee.tax_rule.pk:
            fee.tax_rule = None  # TODO: deprecate

    # Apply rounding to get final total in case no payment fees will be added
    apply_rounding(event.settings.tax_rounding, address, event.currency, [*positions, *fees])
    total = sum([c.price for c in positions]) + sum([f.value for f in fees])

    payments_assigned = Decimal("0.00")
    for p in payment_requests:
        # This algorithm of treating min/max values and fees needs to stay in sync between the following
        # places in the code base:
        # - pretix.base.services.cart.get_fees
        # - pretix.base.services.orders._get_fees
        # - pretix.presale.views.CartMixin.current_selected_payments
        if p.get('min_value') and total - payments_assigned < Decimal(p['min_value']):
            p['payment_amount'] = Decimal('0.00')
            continue

        to_pay = max(total - payments_assigned, Decimal("0.00"))
        if p.get('max_value') and to_pay > Decimal(p['max_value']):
            to_pay = min(to_pay, Decimal(p['max_value']))

        payment_fee = p['pprov'].calculate_fee(to_pay)
        if payment_fee:
            pf = OrderFee(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=payment_fee,
                          internal_type=p['pprov'].identifier)
            pf._calculate_tax(invoice_address=address, event=event)
            fees.append(pf)
            p['fee'] = pf

            # Re-apply rounding as grand total has changed
            apply_rounding(event.settings.tax_rounding, address, event.currency, [*positions, *fees])
            total = sum([c.price for c in positions]) + sum([f.value for f in fees])

            # Re-calculate to_pay as grand total has changed
            to_pay = max(total - payments_assigned, Decimal("0.00"))

            if p.get('max_value') and to_pay > Decimal(p['max_value']):
                to_pay = min(to_pay, Decimal(p['max_value']))

        payments_assigned += to_pay
        p['payment_amount'] = to_pay

    if total != payments_assigned and not require_approval:
        raise OrderError(_("The selected payment methods do not cover the total balance."))

    return fees


def _create_order(event: Event, *, email: str, positions: List[CartPosition], now_dt: datetime,
                  payment_requests: List[dict], sales_channel: SalesChannel, locale: str=None,
                  address: InvoiceAddress=None, meta_info: dict=None, shown_total=None,
                  customer=None, valid_if_pending=False, api_meta: dict=None, tax_rounding_mode=None):
    payments = []

    try:
        validate_memberships_in_order(customer, positions, event, lock=True, testmode=event.testmode)
    except ValidationError as e:
        raise OrderError(e.message)

    require_approval = any(p.requires_approval(invoice_address=address) for p in positions)

    # Final calculation of fees, also performs final rounding
    try:
        fees = _apply_rounding_and_fees(positions, payment_requests, address, meta_info, event, require_approval=require_approval)
    except TaxRule.SaleNotAllowed:
        raise OrderError(error_messages['country_blocked'])

    total = pending_sum = sum([c.price for c in positions]) + sum([c.value for c in fees])

    order = Order(
        status=Order.STATUS_PENDING,
        event=event,
        email=email,
        phone=(meta_info or {}).get('contact_form_data', {}).get('phone'),
        datetime=now_dt,
        locale=get_language_without_region(locale),
        total=total,
        testmode=True if sales_channel.type_instance.testmode_supported and event.testmode else False,
        meta_info=json.dumps(meta_info or {}),
        api_meta=api_meta or {},
        require_approval=require_approval,
        sales_channel=sales_channel,
        customer=customer,
        valid_if_pending=valid_if_pending,
        tax_rounding_mode=tax_rounding_mode or event.settings.tax_rounding,
    )
    if customer:
        order.email_known_to_work = customer.is_verified
    order.set_expires(now_dt, event.subevents.filter(id__in=[p.subevent_id for p in positions]))
    order.save()

    if address:
        if address.order is not None:
            address.pk = None
        address.order = order
        address.save()

    for fee in fees:
        fee.order = order
        fee.save()

    # Safety check: Is the amount we're now going to charge the same amount the user has been shown when they
    # pressed "Confirm purchase"? If not, we should better warn the user and show the confirmation page again.
    # We used to have a *known* case where this happened is if a gift card is used in two concurrent sessions,
    # but this is now a payment error instead. So currently this code branch is usually only triggered by bugs
    # in other places (e.g. tax calculation).
    if shown_total is not None:
        if Decimal(shown_total) != pending_sum:
            raise OrderError(
                _('While trying to place your order, we noticed that the order total has changed. Either one of '
                  'the prices changed just now, or a gift card you used has been used in the meantime. Please '
                  'check the prices below and try again.')
            )

    if payment_requests and not order.require_approval:
        for p in payment_requests:
            if not p.get('multi_use_supported') or p['payment_amount'] > Decimal('0.00'):
                payments.append(order.payments.create(
                    state=OrderPayment.PAYMENT_STATE_CREATED,
                    provider=p['provider'],
                    amount=p['payment_amount'],
                    fee=p.get('fee'),
                    info=json.dumps(p['info_data']),
                    process_initiated=False,
                ))

    orderpositions = OrderPosition.transform_cart_positions(positions, order)
    order.create_transactions(positions=orderpositions, fees=fees, is_new=True)
    order.log_action('pretix.event.order.placed')
    if order.require_approval:
        order.log_action('pretix.event.order.placed.require_approval')
    if meta_info:
        for msg in meta_info.get('confirm_messages', []):
            order.log_action('pretix.event.order.consent', data={'msg': msg})

    order_placed.send(event, order=order, bulk=False)
    return order, payments


def _order_placed_email(event: Event, order: Order, email_template, subject_template,
                        log_entry: str, invoice, payments: List[OrderPayment], is_free=False):
    email_context = get_email_context(event=event, order=order, payments=payments)

    order.send_mail(
        subject_template, email_template, email_context,
        log_entry,
        invoices=[invoice] if invoice else [],
        attach_tickets=True,
        attach_ical=event.settings.mail_attach_ical and (
            not event.settings.mail_attach_ical_paid_only or
            is_free or
            order.valid_if_pending
        ),
        attach_other_files=[a for a in [
            event.settings.get('mail_attachment_new_order', as_type=str, default='')[len('file://'):]
        ] if a],
    )


def _order_placed_email_attendee(event: Event, order: Order, position: OrderPosition, email_template, subject_template,
                                 log_entry: str, is_free=False):
    email_context = get_email_context(event=event, order=order, position=position)

    position.send_mail(
        subject_template, email_template, email_context,
        log_entry,
        invoices=[],
        attach_tickets=True,
        attach_ical=event.settings.mail_attach_ical and (
            not event.settings.mail_attach_ical_paid_only or
            is_free or
            order.valid_if_pending
        ),
        attach_other_files=[a for a in [
            event.settings.get('mail_attachment_new_order', as_type=str, default='')[len('file://'):]
        ] if a],
    )


def _perform_order(event: Event, payment_requests: List[dict], position_ids: List[str],
                   email: str, locale: str, address: int, meta_info: dict=None, sales_channel: str='web',
                   shown_total=None, customer=None, api_meta: dict=None, tax_rounding_mode=None):
    for p in payment_requests:
        p['pprov'] = event.get_payment_providers(cached=True)[p['provider']]
        if not p['pprov']:
            raise OrderError(error_messages['internal'])

    if customer:
        customer = event.organizer.customers.get(pk=customer)

    try:
        sales_channel = event.organizer.sales_channels.get(identifier=sales_channel)
    except SalesChannel.DoesNotExist:
        raise OrderError("Invalid sales channel.")

    if email == settings.PRETIX_EMAIL_NONE_VALUE:
        email = None

    addr = None
    if address is not None:
        try:
            with scopes_disabled():
                addr = InvoiceAddress.objects.get(pk=address)
        except InvoiceAddress.DoesNotExist:
            pass

    requires_seat = Exists(
        SeatCategoryMapping.objects.filter(
            Q(product=OuterRef('item'))
            & (Q(subevent=OuterRef('subevent')) if event.has_subevents else Q(subevent__isnull=True))
        )
    )
    if not event.settings.seating_choice:
        requires_seat = Value(0, output_field=IntegerField())
    positions = CartPosition.objects.annotate(
        requires_seat=requires_seat
    ).filter(
        id__in=position_ids, event=event
    )

    if shown_total is not None and Decimal(shown_total) > Decimal("0.00") and event.currency == "XXX":
        raise OrderError(error_messages['currency_XXX'])

    validate_order.send(
        event,
        payment_provider=payment_requests[0]['provider'] if payment_requests else None,  # only for backwards compatibility
        payments=payment_requests,
        email=email,
        positions=positions,
        locale=locale,
        invoice_address=addr,
        meta_info=meta_info,
        customer=customer,
    )

    valid_if_pending = False
    for recv, result in order_valid_if_pending.send(
            event,
            payments=payment_requests,
            email=email,
            positions=positions,
            locale=locale,
            invoice_address=addr,
            meta_info=meta_info,
            customer=customer,
    ):
        if result:
            valid_if_pending = True

    warnings = []
    any_payment_failed = False

    real_now_dt = now()
    time_machine_now_dt = time_machine_now(real_now_dt)
    err_out = None
    with transaction.atomic(durable=True):
        positions = list(
            positions.select_related('item', 'variation', 'subevent', 'seat', 'addon_to').prefetch_related('addons')
        )
        positions.sort(key=lambda c: c.sort_key)
        if len(positions) == 0:
            raise OrderError(error_messages['empty'])
        if len(position_ids) != len(positions):
            raise OrderError(error_messages['internal'])
        try:
            _check_positions(event, real_now_dt, time_machine_now_dt, positions,
                             address=addr, sales_channel=sales_channel, customer=customer)
        except OrderError as e:
            err_out = e  # Don't raise directly to make sure transaction is committed, as it might have deleted things
        else:
            if 'sleep-after-quota-check' in debugflags_var.get():
                sleep(2)

            order, payment_objs = _create_order(
                event,
                email=email,
                positions=positions,
                now_dt=real_now_dt,
                payment_requests=payment_requests,
                locale=locale,
                address=addr,
                meta_info=meta_info,
                sales_channel=sales_channel,
                shown_total=shown_total,
                customer=customer,
                valid_if_pending=valid_if_pending,
                api_meta=api_meta,
                tax_rounding_mode=tax_rounding_mode,
            )

            try:
                for p in payment_objs:
                    if p.provider == 'free':
                        # Passing lock=False is safe here because it's absolutely impossible for the order to be expired
                        # here before it is even committed.
                        p.confirm(send_mail=False, lock=False, generate_invoice=False)
            except Quota.QuotaExceededException:
                pass
    if err_out:
        raise err_out

    # We give special treatment to GiftCardPayment here because our invoice renderer expects gift cards to already be
    # processed, and because we historically treat gift card orders like free orders with regards to email texts.
    # It would be great to give external gift card plugins the same special treatment, but it feels to risky for now, as
    # (a) there would be no email at all if the plugin fails in a weird way and (b) we'd be able to run into
    # contradictions when a plugin set both execute_payment_needs_user=False as well as requires_invoice_immediately=True
    for p in payment_objs:
        if isinstance(p.payment_provider, GiftCardPayment):
            try:
                p.process_initiated = True
                p.save(update_fields=['process_initiated'])
                p.payment_provider.execute_payment(None, p, is_early_special_case=True)
            except PaymentException as e:
                warnings.append(str(e))
                any_payment_failed = True
            except Exception:
                logger.exception('Error during payment attempt')
            else:
                order.refresh_from_db()

    pending_sum = order.pending_sum
    free_order_flow = (
        payment_objs and
        (
            any(p['provider'] == 'free' for p in payment_requests) or
            all(p['provider'] == 'giftcard' for p in payment_requests)
        ) and
        pending_sum == Decimal('0.00') and
        not order.require_approval
    )

    transmit_invoice_task = order_invoice_transmission_separately(order)
    transmit_invoice_mail = not transmit_invoice_task and order.event.settings.invoice_email_attachment and order.email

    invoice = order.invoices.last()  # Might be generated by plugin already
    if not invoice and invoice_qualified(order):
        invoice_required = (
            event.settings.get('invoice_generate') == 'True' or (
                event.settings.get('invoice_generate') == 'paid' and (
                    any(p['pprov'].requires_invoice_immediately for p in payment_requests) or
                    pending_sum <= Decimal('0.00')
                )
            )
        )
        if invoice_required:
            try:
                invoice = generate_invoice(
                    order,
                    # send_mail will trigger PDF generation later
                    trigger_pdf=not transmit_invoice_mail
                )
                if transmit_invoice_task:
                    transmit_invoice.apply_async(args=(event.pk, invoice.pk, False))
            except Exception as e:
                logger.exception("Could not generate invoice.")
                order.log_action("pretix.event.order.invoice.failed", data={
                    "exception": str(e)
                })

    if order.email:
        if order.require_approval:
            email_template = event.settings.mail_text_order_placed_require_approval
            subject_template = event.settings.mail_subject_order_placed_require_approval
            log_entry = 'pretix.event.order.email.order_placed_require_approval'

            email_attendees = False
        elif free_order_flow:
            email_template = event.settings.mail_text_order_free
            subject_template = event.settings.mail_subject_order_free
            log_entry = 'pretix.event.order.email.order_free'

            email_attendees = event.settings.mail_send_order_free_attendee
            email_attendees_template = event.settings.mail_text_order_free_attendee
            subject_attendees_template = event.settings.mail_subject_order_free_attendee
        else:
            email_template = event.settings.mail_text_order_placed
            subject_template = event.settings.mail_subject_order_placed
            log_entry = 'pretix.event.order.email.order_placed'

            email_attendees = event.settings.mail_send_order_placed_attendee
            email_attendees_template = event.settings.mail_text_order_placed_attendee
            subject_attendees_template = event.settings.mail_subject_order_placed_attendee

        if sales_channel.identifier in event.settings.mail_sales_channel_placed_paid:
            _order_placed_email(
                event,
                order,
                email_template,
                subject_template,
                log_entry,
                invoice if transmit_invoice_mail else None,
                payment_objs,
                is_free=free_order_flow
            )
            if email_attendees:
                for p in order.positions.all():
                    if p.addon_to_id is None and p.attendee_email and p.attendee_email != order.email:
                        _order_placed_email_attendee(event, order, p, email_attendees_template, subject_attendees_template, log_entry,
                                                     is_free=free_order_flow)

    if not any_payment_failed:
        for p in payment_objs:
            if not p.payment_provider.execute_payment_needs_user and not p.process_initiated:
                try:
                    p.process_initiated = True
                    p.save(update_fields=['process_initiated'])
                    resp = p.payment_provider.execute_payment(None, p)
                    if isinstance(resp, str):
                        logger.warning('Payment provider returned URL from execute_payment even though execute_payment_needs_user is not set')
                except PaymentException as e:
                    warnings.append(str(e))
                    any_payment_failed = True
                except Exception:
                    logger.exception('Error during payment attempt')

    if any_payment_failed:
        # Cancel all other payments because their amount might be wrong now.
        for p in payment_objs:
            if p.state == OrderPayment.PAYMENT_STATE_CREATED:
                p.state = OrderPayment.PAYMENT_STATE_CANCELED
                p.save(update_fields=['state'])

    return {
        'order_id': order.id,
        'warnings': warnings,
    }


@receiver(signal=periodic_task)
@scopes_disabled()
def expire_orders(sender, **kwargs):
    event_id = None
    expire = None

    qs = Order.objects.filter(
        expires__lt=now(),
        status=Order.STATUS_PENDING,
        valid_if_pending=False,
        require_approval=False
    ).exclude(
        Exists(
            OrderFee.objects.filter(order_id=OuterRef('pk'), fee_type=OrderFee.FEE_TYPE_CANCELLATION)
        )
    ).prefetch_related('event').order_by('event_id')
    for o in qs:
        if o.event_id != event_id:
            expire = o.event.settings.get('payment_term_expire_automatically', as_type=bool)
            event_id = o.event_id
        if expire and now() >= o.payment_term_expire_date:
            mark_order_expired(o)


@receiver(signal=periodic_task)
@scopes_disabled()
@minimum_interval(minutes_after_success=60)
def send_expiry_warnings(sender, **kwargs):
    today = now().replace(hour=0, minute=0, second=0)
    days = None
    settings = None
    event_id = None

    for o in Order.objects.filter(
            expires__gte=today, expiry_reminder_sent=False, status=Order.STATUS_PENDING,
            datetime__lte=now() - timedelta(hours=2), require_approval=False
    ).only('pk', 'event_id', 'expires').order_by('event_id'):

        lp = o.payments.last()
        if (
                lp and
                lp.state in [OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING] and
                lp.payment_provider and
                lp.payment_provider.prevent_reminder_mail(o, lp)
        ):
            continue

        if event_id != o.event_id:
            settings = o.event.settings
            days = cache.get_or_set('{}:{}:setting_mail_days_order_expire_warning'.format('event', o.event_id),
                                    default=lambda: settings.get('mail_days_order_expire_warning', as_type=int),
                                    timeout=3600)
            event_id = o.event_id

        if days and (o.expires - today).days <= days:
            with transaction.atomic():
                o = Order.objects.select_related('event').select_for_update(of=OF_SELF).get(pk=o.pk)
                if o.status != Order.STATUS_PENDING or o.expiry_reminder_sent:
                    # Race condition
                    continue

                with language(o.locale, settings.region):
                    o.expiry_reminder_sent = True
                    o.save(update_fields=['expiry_reminder_sent'])
                    email_context = get_email_context(event=o.event, order=o)
                    can_autoexpire = (
                        settings.payment_term_expire_automatically and
                        not o.valid_if_pending and
                        not o.fees.filter(fee_type=OrderFee.FEE_TYPE_CANCELLATION).exists()
                    )
                    if can_autoexpire:
                        email_template = settings.mail_text_order_expire_warning
                        email_subject = settings.mail_subject_order_expire_warning
                    else:
                        email_template = settings.mail_text_order_pending_warning
                        email_subject = settings.mail_subject_order_pending_warning

                    o.send_mail(
                        email_subject, email_template, email_context,
                        'pretix.event.order.email.expire_warning_sent'
                    )


@receiver(signal=periodic_task)
@scopes_disabled()
def send_download_reminders(sender, **kwargs):
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    qs = Order.objects.annotate(
        first_date=Coalesce(
            Min('all_positions__subevent__date_from'),
            F('event__date_from')
        )
    ).filter(
        download_reminder_sent=False,
        datetime__lte=now() - timedelta(hours=2),
        first_date__gte=today,
    ).only(
        'pk', 'event_id', 'sales_channel', 'datetime',
    ).order_by('event_id')
    event_id = None
    days = None
    event = None

    for o in qs:
        if o.event_id != event_id:
            days = o.event.settings.get('mail_days_download_reminder', as_type=int)
            event = o.event
            event_id = o.event_id

        if days is None:
            continue

        if o.sales_channel.identifier not in event.settings.mail_sales_channel_download_reminder:
            continue

        reminder_date = (o.first_date - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        if now() < reminder_date or o.datetime > reminder_date:
            continue

        with transaction.atomic():
            o = Order.objects.select_for_update(of=OF_SELF).get(pk=o.pk)
            if o.download_reminder_sent:
                # Race condition
                continue
            positions = list(o.positions_with_tickets)
            if not positions:
                continue

            if not o.ticket_download_available:
                continue

            if o.status != Order.STATUS_PAID:
                if o.status != Order.STATUS_PENDING or o.require_approval or (not o.valid_if_pending and not o.event.settings.ticket_download_pending):
                    continue

            with language(o.locale, o.event.settings.region):
                o.download_reminder_sent = True
                o.save(update_fields=['download_reminder_sent'])
                email_template = event.settings.mail_text_download_reminder
                email_subject = event.settings.mail_subject_download_reminder
                email_context = get_email_context(event=event, order=o)
                o.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.download_reminder_sent',
                    attach_tickets=True
                )

                if event.settings.mail_send_download_reminder_attendee:
                    for p in positions:
                        if p.subevent_id:
                            reminder_date = (p.subevent.date_from - timedelta(days=days)).replace(
                                hour=0, minute=0, second=0, microsecond=0
                            )
                            if now() < reminder_date:
                                continue
                        if p.addon_to_id is None and p.attendee_email and p.attendee_email != o.email:
                            email_template = event.settings.mail_text_download_reminder_attendee
                            email_subject = event.settings.mail_subject_download_reminder_attendee
                            email_context = get_email_context(event=event, order=o, position=p)
                            o.send_mail(
                                email_subject, email_template, email_context,
                                'pretix.event.order.email.download_reminder_sent',
                                attach_tickets=True, position=p
                            )


def notify_user_changed_order(order, user=None, auth=None, invoices=[]):
    with language(order.locale, order.event.settings.region):
        email_template = order.event.settings.mail_text_order_changed
        email_context = get_email_context(event=order.event, order=order)
        email_subject = order.event.settings.mail_subject_order_changed
        order.send_mail(
            email_subject, email_template, email_context,
            'pretix.event.order.email.order_changed', user, auth=auth, invoices=invoices, attach_tickets=True,
        )


class OrderChangeManager:
    error_messages = {
        'product_without_variation': gettext_lazy('You need to select a variation of the product.'),
        'quota': gettext_lazy('The quota {name} does not have enough capacity left to perform the operation.'),
        'quota_missing': gettext_lazy('There is no quota defined that allows this operation.'),
        'product_invalid': gettext_lazy('The selected product is not active or has no price set.'),
        'complete_cancel': gettext_lazy('This operation would leave the order empty. Please cancel the order itself instead.'),
        'paid_to_free_exceeded': gettext_lazy(
            'This operation would make the order free and therefore immediately paid, however '
            'no quota is available.'
        ),
        'addon_to_required': gettext_lazy('This is an add-on product, please select the base position it should be added to.'),
        'addon_invalid': gettext_lazy('The selected base position does not allow you to add this product as an add-on.'),
        'subevent_required': gettext_lazy('You need to choose a subevent for the new position.'),
        'seat_unavailable': gettext_lazy('The selected seat "{seat}" is not available.'),
        'seat_subevent_mismatch': gettext_lazy(
            'You selected seat "{seat}" for a date that does not match the selected ticket date. Please choose a seat again.'
        ),
        'seat_required': gettext_lazy('The selected product requires you to select a seat.'),
        'seat_forbidden': gettext_lazy('The selected product does not allow to select a seat.'),
        'tax_rule_country_blocked': gettext_lazy('The selected country is blocked by your tax rule.'),
        'gift_card_change': gettext_lazy('You cannot change the price of a position that has been used to issue a gift card.'),
        'max_items_per_product': ngettext_lazy(
            "You cannot select more than %(max)s item of the product %(product)s.",
            "You cannot select more than %(max)s items of the product %(product)s.",
            "max"
        ),
        'min_items_per_product': ngettext_lazy(
            "You need to select at least %(min)s item of the product %(product)s.",
            "You need to select at least %(min)s items of the product %(product)s.",
            "min"
        ),
        'max_order_size': gettext_lazy('Orders cannot have more than %(max)s positions.'),
    }
    ItemOperation = namedtuple('ItemOperation', ('position', 'item', 'variation'))
    SubeventOperation = namedtuple('SubeventOperation', ('position', 'subevent'))
    SeatOperation = namedtuple('SubeventOperation', ('position', 'seat'))
    PriceOperation = namedtuple('PriceOperation', ('position', 'price', 'price_diff'))
    TaxRuleOperation = namedtuple('TaxRuleOperation', ('position', 'tax_rule'))
    MembershipOperation = namedtuple('MembershipOperation', ('position', 'membership'))
    CancelOperation = namedtuple('CancelOperation', ('position', 'price_diff'))
    AddOperation = namedtuple('AddOperation', ('item', 'variation', 'price', 'addon_to', 'subevent', 'seat', 'membership',
                                               'valid_from', 'valid_until', 'is_bundled', 'result'))
    SplitOperation = namedtuple('SplitOperation', ('position',))
    FeeValueOperation = namedtuple('FeeValueOperation', ('fee', 'value', 'price_diff'))
    AddFeeOperation = namedtuple('AddFeeOperation', ('fee', 'price_diff'))
    CancelFeeOperation = namedtuple('CancelFeeOperation', ('fee', 'price_diff'))
    RegenerateSecretOperation = namedtuple('RegenerateSecretOperation', ('position',))
    ChangeSecretOperation = namedtuple('ChangeSecretOperation', ('position', 'new_secret'))
    ChangeValidFromOperation = namedtuple('ChangeValidFromOperation', ('position', 'valid_from'))
    ChangeValidUntilOperation = namedtuple('ChangeValidUntilOperation', ('position', 'valid_until'))
    AddBlockOperation = namedtuple('AddBlockOperation', ('position', 'block_name', 'ignore_from_quota_while_blocked'))
    RemoveBlockOperation = namedtuple('RemoveBlockOperation', ('position', 'block_name', 'ignore_from_quota_while_blocked'))
    ForceRecomputeOperation = namedtuple('ForceRecomputeOperation', tuple())

    class AddPositionResult:
        _position: Optional[OrderPosition]

        def __init__(self):
            self._position = None

        @property
        def position(self) -> OrderPosition:
            if self._position is None:
                raise RuntimeError("Order position has not been created yet. Call commit() first on OrderChangeManager.")
            return self._position

    def __init__(self, order: Order, user=None, auth=None, notify=True, reissue_invoice=True, allow_blocked_seats=False):
        self.order = order
        self.user = user
        self.auth = auth
        self.event = order.event
        self.split_order = None
        self.reissue_invoice = reissue_invoice
        self.allow_blocked_seats = allow_blocked_seats
        self._committed = False
        self._totaldiff_guesstimate = 0
        self._quotadiff = Counter()
        self._seatdiff = Counter()
        self._operations = []
        self.notify = notify
        self._invoice_dirty = False
        self._invoices = []

    def change_item(self, position: OrderPosition, item: Item, variation: Optional[ItemVariation]):
        if (not variation and item.has_variations) or (variation and variation.item_id != item.pk):
            raise OrderError(self.error_messages['product_without_variation'])

        new_quotas = (variation.quotas.filter(subevent=position.subevent)
                      if variation else item.quotas.filter(subevent=position.subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        self._quotadiff.update(new_quotas)
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.ItemOperation(position, item, variation))

    def change_seat(self, position: OrderPosition, seat: Optional[Seat]):
        if isinstance(seat, str):
            subev = None
            if self.event.has_subevents:
                subev = position.subevent
                for p in self._operations:
                    if isinstance(p, self.SubeventOperation) and p.position == position:
                        subev = p.subevent
            try:
                seat = Seat.objects.get(
                    event=self.event,
                    subevent=subev,
                    seat_guid=seat
                )
            except Seat.DoesNotExist:
                raise OrderError(error_messages['seat_invalid'])
        if position.seat:
            self._seatdiff.subtract([position.seat])
        if seat:
            self._seatdiff.update([seat])
        self._operations.append(self.SeatOperation(position, seat))

    def change_membership(self, position: OrderPosition, membership: Membership):
        self._operations.append(self.MembershipOperation(position, membership))

    def change_subevent(self, position: OrderPosition, subevent: SubEvent):
        try:
            price = get_price(position.item, position.variation, voucher=position.voucher, subevent=subevent,
                              invoice_address=self._invoice_address)
        except TaxRule.SaleNotAllowed:
            raise OrderError(self.error_messages['tax_rule_country_blocked'])

        if price is None:  # NOQA
            raise OrderError(self.error_messages['product_invalid'])

        new_quotas = (position.variation.quotas.filter(subevent=subevent)
                      if position.variation else position.item.quotas.filter(subevent=subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        self._quotadiff.update(new_quotas)
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.SubeventOperation(position, subevent))
        self._invoice_dirty = True

    def change_item_and_subevent(self, position: OrderPosition, item: Item, variation: Optional[ItemVariation],
                                 subevent: SubEvent):
        if (not variation and item.has_variations) or (variation and variation.item_id != item.pk):
            raise OrderError(self.error_messages['product_without_variation'])

        try:
            price = get_price(item, variation, voucher=position.voucher, subevent=subevent,
                              invoice_address=self._invoice_address)
        except TaxRule.SaleNotAllowed:
            raise OrderError(self.error_messages['tax_rule_country_blocked'])

        if price is None:  # NOQA
            raise OrderError(self.error_messages['product_invalid'])

        new_quotas = (variation.quotas.filter(subevent=subevent)
                      if variation else item.quotas.filter(subevent=subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        self._quotadiff.update(new_quotas)
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.ItemOperation(position, item, variation))
        self._operations.append(self.SubeventOperation(position, subevent))
        self._invoice_dirty = True

    def regenerate_secret(self, position: OrderPosition):
        self._operations.append(self.RegenerateSecretOperation(position))

    def change_ticket_secret(self, position: OrderPosition, new_secret: str):
        self._operations.append(self.ChangeSecretOperation(position, new_secret))

    def change_valid_from(self, position: OrderPosition, new_value: datetime):
        self._operations.append(self.ChangeValidFromOperation(position, new_value))

    def change_valid_until(self, position: OrderPosition, new_value: datetime):
        self._operations.append(self.ChangeValidUntilOperation(position, new_value))

    def add_block(self, position: OrderPosition, block_name: str, ignore_from_quota_while_blocked=None):
        self._operations.append(self.AddBlockOperation(position, block_name, ignore_from_quota_while_blocked))

    def remove_block(self, position: OrderPosition, block_name: str, ignore_from_quota_while_blocked=None):
        self._operations.append(self.RemoveBlockOperation(position, block_name, ignore_from_quota_while_blocked))

    def change_price(self, position: OrderPosition, price: Decimal):
        tax_rule = self._current_tax_rules().get(position.pk, position.tax_rule) or TaxRule.zero()
        price = tax_rule.tax(price, base_price_is='gross', invoice_address=self._invoice_address,
                             force_fixed_gross_price=True)

        if position.issued_gift_cards.exists():
            raise OrderError(self.error_messages['gift_card_change'])

        self._totaldiff_guesstimate += price.gross - position.gross_price_before_rounding

        if self.order.event.settings.invoice_include_free or price.gross != Decimal('0.00') or position.price != Decimal('0.00'):
            self._invoice_dirty = True

        self._operations.append(self.PriceOperation(position, price, price.gross - position.price))

    def change_tax_rule(self, position_or_fee, tax_rule: TaxRule):
        self._operations.append(self.TaxRuleOperation(position_or_fee, tax_rule))
        self._invoice_dirty = True

    def _current_tax_rules(self):
        tax_rules = {}
        for p in self._operations:
            if isinstance(p, self.TaxRuleOperation):
                tax_rules[p.position.pk] = p.tax_rule
            elif isinstance(p, self.ItemOperation):
                tax_rules[p.position.pk] = p.item.tax_rule
        return tax_rules

    def recalculate_taxes(self, keep='net'):
        positions = self.order.positions.select_related('item', 'item__tax_rule')
        ia = self._invoice_address
        tax_rules = self._current_tax_rules()
        self._operations.append(self.ForceRecomputeOperation())

        for pos in positions:
            tax_rule = tax_rules.get(pos.pk, pos.tax_rule)
            if not tax_rule:
                continue
            if not pos.price:
                continue

            try:
                new_rate = tax_rule.tax_rate_for(ia)
                new_code = tax_rule.tax_code_for(ia)
            except TaxRule.SaleNotAllowed:
                raise OrderError(error_messages['tax_rule_country_blocked'])
            # We use override_tax_rate to make sure .tax() doesn't get clever and re-adjusts the pricing itself
            if new_rate != pos.tax_rate or new_code != pos.tax_code:
                if keep == 'net':
                    new_tax = tax_rule.tax(pos.price - pos.tax_value, base_price_is='net', currency=self.event.currency,
                                           override_tax_rate=new_rate, override_tax_code=new_code)
                else:
                    new_tax = tax_rule.tax(pos.price, base_price_is='gross', currency=self.event.currency,
                                           override_tax_rate=new_rate, override_tax_code=new_code)
                self._totaldiff_guesstimate += new_tax.gross - pos.price
                self._operations.append(self.PriceOperation(pos, new_tax, new_tax.gross - pos.price))
                self._invoice_dirty = True

    def cancel_fee(self, fee: OrderFee):
        self._totaldiff_guesstimate -= fee.value
        self._operations.append(self.CancelFeeOperation(fee, -fee.value))
        self._invoice_dirty = True

    def add_fee(self, fee: OrderFee):
        self._totaldiff_guesstimate += fee.value
        self._invoice_dirty = True
        self._operations.append(self.AddFeeOperation(fee, fee.value))

    def change_fee(self, fee: OrderFee, value: Decimal):
        value = (fee.tax_rule or TaxRule.zero()).tax(value, base_price_is='gross', invoice_address=self._invoice_address,
                                                     force_fixed_gross_price=True)
        self._totaldiff_guesstimate += value.gross - fee.value
        self._invoice_dirty = True
        self._operations.append(self.FeeValueOperation(fee, value, value.gross - fee.value))

    def cancel(self, position: OrderPosition):
        self._totaldiff_guesstimate -= position.price
        self._quotadiff.subtract(position.quotas)
        self._operations.append(self.CancelOperation(position, -position.price))
        if position.seat:
            self._seatdiff.subtract([position.seat])

        if self.order.event.settings.invoice_include_free or position.price != Decimal('0.00'):
            self._invoice_dirty = True

    def add_position(self, item: Item, variation: ItemVariation, price: Decimal, addon_to: OrderPosition = None,
                     subevent: SubEvent = None, seat: Seat = None, membership: Membership = None,
                     valid_from: datetime = None, valid_until: datetime = None) -> 'OrderChangeManager.AddPositionResult':
        if isinstance(seat, str):
            if not seat:
                seat = None
            else:
                try:
                    seat = Seat.objects.get(
                        event=self.event,
                        subevent=subevent,
                        seat_guid=seat
                    )
                except Seat.DoesNotExist:
                    raise OrderError(error_messages['seat_invalid'])

        try:
            if price is None:
                price = get_price(item, variation, subevent=subevent, invoice_address=self._invoice_address)
            elif not isinstance(price, TaxedPrice):
                price = item.tax(price, base_price_is='gross', invoice_address=self._invoice_address,
                                 force_fixed_gross_price=True)
        except TaxRule.SaleNotAllowed:
            raise OrderError(self.error_messages['tax_rule_country_blocked'])

        is_bundled = False
        if price is None:
            raise OrderError(self.error_messages['product_invalid'])
        if item.variations.exists() and not variation:
            raise OrderError(self.error_messages['product_without_variation'])
        if not addon_to and item.category and item.category.is_addon:
            raise OrderError(self.error_messages['addon_to_required'])
        if addon_to:
            if not item.category or item.category_id not in addon_to.item.addons.values_list('addon_category', flat=True):
                if addon_to.item.bundles.filter(bundled_item=item, bundled_variation=variation).exists():
                    is_bundled = True
                else:
                    raise OrderError(self.error_messages['addon_invalid'])
        if self.order.event.has_subevents and not subevent:
            raise OrderError(self.error_messages['subevent_required'])

        seated = item.seat_category_mappings.filter(subevent=subevent).exists()
        if seated and not seat and self.event.settings.seating_choice:
            raise OrderError(self.error_messages['seat_required'])
        elif not seated and seat:
            raise OrderError(self.error_messages['seat_forbidden'])
        if seat and subevent and seat.subevent_id != subevent.pk:
            raise OrderError(self.error_messages['seat_subevent_mismatch'].format(seat=seat.name))

        new_quotas = (variation.quotas.filter(subevent=subevent)
                      if variation else item.quotas.filter(subevent=subevent))
        if not new_quotas:
            raise OrderError(self.error_messages['quota_missing'])

        if self.order.event.settings.invoice_include_free or price.gross != Decimal('0.00'):
            self._invoice_dirty = True

        self._totaldiff_guesstimate += price.gross
        self._quotadiff.update(new_quotas)
        if seat:
            self._seatdiff.update([seat])

        result = self.AddPositionResult()
        self._operations.append(self.AddOperation(item, variation, price, addon_to, subevent, seat, membership,
                                                  valid_from, valid_until, is_bundled, result))
        return result

    def split(self, position: OrderPosition):
        if self.order.event.settings.invoice_include_free or position.price != Decimal('0.00'):
            self._invoice_dirty = True

        self._operations.append(self.SplitOperation(position))
        for a in position.addons.all():
            self._operations.append(self.SplitOperation(a))

    def set_addons(self, addons, limit_main_positions=None):
        """
        This is a convenience method to change the add-on products selected on an order. The input structure is similar
        to CartManager.set_addons. It will automatically compute the correct operations to add, cancel, or change
        positions on the order. Every existing add-on not in the input will be canceled. Availability of the
        products is validated (with some exceptions).

        :param addons: A list of dictionaries with the keys ``"addon_to"``, ``"item"``, ``"variation"`` (all ID values),
                       ``"count"``, and ``"price"``.
        :param limit_main_positions: By default, the method works on all methods of the order. If you set this to a
                                     queryset or a list of positions, all other positions and their add-ons will be kept
                                     untouched.
        """
        if self._operations:
            raise ValueError("Setting addons should be the first/only operation")

        # Prepare containers for min/max check of products
        item_counts = Counter()
        for p in self.order.positions.all():
            item_counts[p.item] += 1

        # Prepare various containers to hold data later
        current_addons = defaultdict(lambda: defaultdict(list))  # OrderPos -> currently attached add-ons
        input_addons = defaultdict(Counter)  # OrderPos -> final desired set of add-ons
        selected_addons = defaultdict(Counter)  # OrderPos, ItemAddOn -> final desired set of add-ons
        opcache = {}  # OrderPos.pk -> OrderPos
        quota_diff = Counter()  # Quota -> Number of usages
        available_categories = defaultdict(set)  # OrderPos -> Category IDs to choose from
        price_included = defaultdict(dict)  # OrderPos -> CategoryID -> bool(price is included)
        if isinstance(limit_main_positions, QuerySet):
            toplevel_qs = limit_main_positions
        elif limit_main_positions is not None:
            toplevel_qs = self.order.positions.filter(pk__in=[p.pk for p in limit_main_positions])
        else:
            toplevel_qs = self.order.positions
        toplevel_op = toplevel_qs.filter(
            addon_to__isnull=True
        ).prefetch_related(
            'addons', 'item__addons', 'item__addons__addon_category'
        ).select_related('item', 'variation')

        _items_cache = {
            i.pk: i
            for i in self.event.items.select_related('category').prefetch_related(
                'addons', 'bundles', 'addons__addon_category', 'quotas'
            ).annotate(
                has_variations=Count('variations'),
            ).filter(
                id__in=[a['item'] for a in addons]
            ).order_by()
        }
        _variations_cache = {
            v.pk: v
            for v in ItemVariation.objects.filter(item__event=self.event).prefetch_related(
                'quotas'
            ).select_related('item', 'item__event').filter(
                id__in=[a['variation'] for a in addons if a.get('variation')]
            ).order_by()
        }

        # Prefill some of the cache containers
        for op in toplevel_op:
            if op.canceled:
                continue
            available_categories[op.pk] = {iao.addon_category_id for iao in op.item.addons.all()}
            price_included[op.pk] = {iao.addon_category_id: iao.price_included for iao in op.item.addons.all()}
            opcache[op.pk] = op
            for a in op.addons.all():
                if a.canceled:
                    continue

                if not a.is_bundled:
                    current_addons[op][a.item_id, a.variation_id].append(a)

        # Create operations, perform various checks
        for a in addons:
            # Check whether the specified items are part of what we just fetched from the database
            # If they are not, the user supplied item IDs which either do not exist or belong to
            # a different event
            if a['item'] not in _items_cache or (a['variation'] and a['variation'] not in _variations_cache):
                raise OrderError(error_messages['not_for_sale'])

            # Only attach addons to things that are actually in this user's cart
            if a['addon_to'] not in opcache:
                raise OrderError(error_messages['addon_invalid_base'])

            op = opcache[a['addon_to']]
            item = _items_cache[a['item']]
            subevent = op.subevent  # for now, we might lift this requirement later
            variation = _variations_cache[a['variation']] if a['variation'] is not None else None

            if item.category_id not in available_categories[op.pk]:
                raise OrderError(error_messages['addon_invalid_base'])

            # Fetch all quotas. If there are no quotas, this item is not allowed to be sold.
            quotas = list(item.quotas.filter(subevent=subevent)
                          if variation is None else variation.quotas.filter(subevent=subevent))
            if not quotas:
                raise OrderError(error_messages['unavailable'])

            if (a['item'], a['variation']) in input_addons[op.id]:
                raise OrderError(error_messages['addon_duplicate_item'])

            if item.require_voucher or item.hide_without_voucher or (variation and variation.hide_without_voucher):
                raise OrderError(error_messages['voucher_required'])

            if not item.is_available() or (variation and not variation.is_available()):
                raise OrderError(error_messages['unavailable'])

            if not item.all_sales_channels:
                if self.order.sales_channel.identifier not in (s.identifier for s in item.limit_sales_channels.all()):
                    raise OrderError(error_messages['unavailable'])

            if variation and not variation.all_sales_channels:
                if self.order.sales_channel.identifier not in (s.identifier for s in variation.limit_sales_channels.all()):
                    raise OrderError(error_messages['unavailable'])

            if subevent and item.pk in subevent.item_overrides and not subevent.item_overrides[item.pk].is_available():
                raise OrderError(error_messages['not_for_sale'])

            if subevent and variation and variation.pk in subevent.var_overrides and \
                    not subevent.var_overrides[variation.pk].is_available():
                raise OrderError(error_messages['not_for_sale'])

            if item.has_variations and not variation:
                raise OrderError(error_messages['not_for_sale'])

            if variation and variation.item_id != item.pk:
                raise OrderError(error_messages['not_for_sale'])

            if subevent and subevent.presale_start and now() < subevent.presale_start:
                raise OrderError(error_messages['not_started'])

            if (subevent and subevent.presale_has_ended) or self.event.presale_has_ended:
                raise OrderError(error_messages['ended'])

            if item.require_bundling:
                raise OrderError(error_messages['unavailable'])

            input_addons[op.id][a['item'], a['variation']] = a.get('count', 1)
            selected_addons[op.id, item.category_id][a['item'], a['variation']] = a.get('count', 1)

            if price_included[op.pk].get(item.category_id) or (op.voucher_id and op.voucher.all_addons_included):
                price = TAXED_ZERO
            else:
                price = get_price(
                    item, variation, voucher=None, custom_price=a.get('price'), subevent=op.subevent,
                    custom_price_is_net=self.event.settings.display_net_prices,
                    invoice_address=self._invoice_address,
                )

            if a.get('count', 1) > len(current_addons[op][a['item'], a['variation']]):
                # This add-on is new, add it to the cart
                for quota in quotas:
                    quota_diff[quota] += a.get('count', 1) - len(current_addons[op][a['item'], a['variation']])

                for i in range(a.get('count', 1) - len(current_addons[op][a['item'], a['variation']])):
                    self.add_position(
                        item=item, variation=variation, price=price,
                        addon_to=op, subevent=op.subevent, seat=None,
                    )
                    item_counts[item] += 1

        # Detect removed add-ons and create RemoveOperations
        for cp, al in list(current_addons.items()):
            for k, v in al.items():
                input_num = input_addons[cp.id].get(k, 0)
                current_num = len(current_addons[cp].get(k, []))
                if input_num < current_num:
                    for a in current_addons[cp][k][:current_num - input_num]:
                        if a.canceled:
                            continue
                        is_unavailable = (
                            # If an item is no longer available due to time, it should usually also be no longer
                            # user-removable, because e.g. the stock has already been ordered.
                            # We always pass has_voucher=True because if a product now requires a voucher, it usually does
                            # not mean it should be unremovable for others.
                            # This also prevents accidental removal through the UI because a hidden product will no longer
                            # be part of the input.
                            (a.variation and a.variation.unavailability_reason(has_voucher=True, subevent=a.subevent))
                            or (a.variation and not a.variation.all_sales_channels and not a.variation.limit_sales_channels.contains(self.order.sales_channel))
                            or a.item.unavailability_reason(has_voucher=True, subevent=a.subevent)
                            or (
                                not a.item.all_sales_channels and
                                not a.item.limit_sales_channels.contains(self.order.sales_channel)
                            )
                        )
                        if is_unavailable:
                            # "Re-select" add-on
                            selected_addons[cp.id, a.item.category_id][a.item_id, a.variation_id] += 1
                            continue
                        if a.checkins.filter(list__consider_tickets_used=True).exists():
                            raise OrderError(
                                error_messages['addon_already_checked_in'] % {
                                    'addon': str(a.item.name),
                                }
                            )
                        self.cancel(a)
                        item_counts[a.item] -= 1

        # Check constraints on the add-on combinations
        for op in toplevel_op:
            item = op.item
            for iao in item.addons.all():
                selected = selected_addons[op.id, iao.addon_category_id]
                n_per_i = Counter()
                for (i, v), c in selected.items():
                    n_per_i[i] += c
                if sum(selected.values()) > iao.max_count:
                    raise OrderError(
                        error_messages['addon_max_count'] % {
                            'base': str(item.name),
                            'max': iao.max_count,
                            'cat': str(iao.addon_category.name),
                        }
                    )
                elif sum(selected.values()) < iao.min_count:
                    raise OrderError(
                        error_messages['addon_min_count'] % {
                            'base': str(item.name),
                            'min': iao.min_count,
                            'cat': str(iao.addon_category.name),
                        }
                    )
                elif any(v > 1 for v in n_per_i.values()) and not iao.multi_allowed:
                    raise OrderError(
                        error_messages['addon_no_multi'] % {
                            'base': str(item.name),
                            'cat': str(iao.addon_category.name),
                        }
                    )

        for item, count in item_counts.items():
            if count == 0:
                continue

            if item.max_per_order and count > item.max_per_order:
                raise OrderError(
                    self.error_messages['max_items_per_product'] % {
                        'max': item.max_per_order,
                        'product': item.name
                    }
                )

            if item.min_per_order and count < item.min_per_order:
                raise OrderError(
                    self.error_messages['min_items_per_product'] % {
                        'min': item.min_per_order,
                        'product': item.name
                    }
                )

    def _check_seats(self):
        for seat, diff in self._seatdiff.items():
            if diff <= 0:
                continue
            if not seat.is_available(sales_channel=self.order.sales_channel, ignore_distancing=True, always_allow_blocked=self.allow_blocked_seats) or diff > 1:
                raise OrderError(self.error_messages['seat_unavailable'].format(seat=seat.name))

        if self.event.has_subevents:
            state = {}
            for p in self.order.positions.all():
                state[p] = {'seat': p.seat, 'subevent': p.subevent}
            for op in self._operations:
                if isinstance(op, self.SeatOperation):
                    state[op.position]['seat'] = op.seat
                elif isinstance(op, self.SubeventOperation):
                    state[op.position]['subevent'] = op.subevent
            for v in state.values():
                if v['seat'] and v['seat'].subevent_id != v['subevent'].pk:
                    raise OrderError(self.error_messages['seat_subevent_mismatch'].format(seat=v['seat'].name))

    def _check_quotas(self):
        qa = QuotaAvailability()
        qa.queue(*[k for k, v in self._quotadiff.items() if v > 0])
        qa.compute()
        for quota, diff in self._quotadiff.items():
            if diff <= 0:
                continue
            avail = qa.results[quota]
            if avail[0] != Quota.AVAILABILITY_OK or (avail[1] is not None and avail[1] < diff):
                raise OrderError(self.error_messages['quota'].format(name=quota.name))

    def _check_paid_price_change(self, totaldiff):
        if self.order.status == Order.STATUS_PAID and totaldiff > 0:
            if self.order.pending_sum > Decimal('0.00'):
                self.order.status = Order.STATUS_PENDING
                self.order.set_expires(
                    now(),
                    self.order.event.subevents.filter(id__in=self.order.positions.values_list('subevent_id', flat=True))
                )
                self.order.save()
        elif self.order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and totaldiff < 0:
            if self.order.pending_sum <= Decimal('0.00') and not self.order.require_approval:
                self.order.status = Order.STATUS_PAID
                self.order.save()
            elif self.open_payment:
                try:
                    self.open_payment.payment_provider.cancel_payment(self.open_payment)
                    self.order.log_action(
                        'pretix.event.order.payment.canceled',
                        {
                            'local_id': self.open_payment.local_id,
                            'provider': self.open_payment.provider,
                        },
                        user=self.user,
                        auth=self.auth
                    )
                except PaymentException as e:
                    self.order.log_action(
                        'pretix.event.order.payment.canceled.failed',
                        {
                            'local_id': self.open_payment.local_id,
                            'provider': self.open_payment.provider,
                            'error': str(e)
                        },
                        user=self.user,
                        auth=self.auth
                    )
        elif self.order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and totaldiff > 0:
            if self.open_payment:
                try:
                    self.open_payment.payment_provider.cancel_payment(self.open_payment)
                    self.order.log_action('pretix.event.order.payment.canceled', {
                        'local_id': self.open_payment.local_id,
                        'provider': self.open_payment.provider,
                    }, user=self.user, auth=self.auth)
                except PaymentException as e:
                    self.order.log_action(
                        'pretix.event.order.payment.canceled.failed',
                        {
                            'local_id': self.open_payment.local_id,
                            'provider': self.open_payment.provider,
                            'error': str(e)
                        },
                        user=self.user,
                        auth=self.auth,
                    )

    def _check_paid_to_free(self, totaldiff):
        if self.event.currency == 'XXX' and self.order.total + totaldiff > Decimal("0.00"):
            raise OrderError(error_messages['currency_XXX'])

        if self.order.total == 0 and (totaldiff < 0 or (self.split_order and self.split_order.total > 0)) and not self.order.require_approval:
            if not self.order.fees.exists() and not self.order.positions.exists():
                # The order is completely empty now, so we cancel it.
                self.order.status = Order.STATUS_CANCELED
                self.order.save(update_fields=['status'])
                order_canceled.send(self.order.event, order=self.order)
            elif self.order.status != Order.STATUS_CANCELED:
                # if the order becomes free, mark it paid using the 'free' provider
                # this could happen if positions have been made cheaper or removed (totaldiff < 0)
                # or positions got split off to a new order (split_order with positive total)
                p = self.order.payments.create(
                    state=OrderPayment.PAYMENT_STATE_CREATED,
                    provider='free',
                    amount=0,
                    fee=None
                )
                try:
                    p.confirm(send_mail=False, count_waitinglist=False, user=self.user, auth=self.auth)
                except Quota.QuotaExceededException:
                    raise OrderError(self.error_messages['paid_to_free_exceeded'])

        if self.split_order and self.split_order.total == 0 and not self.split_order.require_approval:
            p = self.split_order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CREATED,
                provider='free',
                amount=0,
                fee=None
            )
            try:
                p.confirm(send_mail=False, count_waitinglist=False, user=self.user, auth=self.auth)
            except Quota.QuotaExceededException:
                raise OrderError(self.error_messages['paid_to_free_exceeded'])

    def _perform_operations(self):
        nextposid = self.order.all_positions.aggregate(m=Max('positionid'))['m'] + 1
        split_positions = []
        secret_dirty = set()
        position_cache = {}
        fee_cache = {}

        for op in self._operations:
            if isinstance(op, self.ItemOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.item', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'old_item': position.item.pk,
                    'old_variation': position.variation.pk if position.variation else None,
                    'new_item': op.item.pk,
                    'new_variation': op.variation.pk if op.variation else None,
                    'old_price': position.price,
                    'addon_to': position.addon_to_id,
                    'new_price': position.price
                })
                position.item = op.item
                position.variation = op.variation
                position._calculate_tax()

                if position.voucher_budget_use is not None and position.voucher and not position.addon_to_id:
                    listed_price = get_listed_price(position.item, position.variation, position.subevent)
                    if not position.item.tax_rule or position.item.tax_rule.price_includes_tax:
                        price_after_voucher = max(position.price, position.voucher.calculate_price(listed_price))
                    else:
                        price_after_voucher = max(position.price - position.tax_value, position.voucher.calculate_price(listed_price))
                    position.voucher_budget_use = max(listed_price - price_after_voucher, Decimal('0.00'))
                secret_dirty.add(position)
                position.save()
            elif isinstance(op, self.MembershipOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.membership', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'old_membership_id': position.used_membership_id,
                    'new_membership_id': op.membership.pk if op.membership else None,
                })
                position.used_membership = op.membership
                position.save()
            elif isinstance(op, self.SeatOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.seat', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'old_seat': position.seat.name if position.seat else "-",
                    'new_seat': op.seat.name if op.seat else "-",
                    'old_seat_id': position.seat.pk if position.seat else None,
                    'new_seat_id': op.seat.pk if op.seat else None,
                })
                position.seat = op.seat
                secret_dirty.add(position)
                position.save()
            elif isinstance(op, self.SubeventOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.subevent', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'old_subevent': position.subevent.pk,
                    'new_subevent': op.subevent.pk,
                    'old_price': position.price,
                    'new_price': position.price
                })
                position.subevent = op.subevent
                secret_dirty.add(position)
                if position.voucher_budget_use is not None and position.voucher and not position.addon_to_id:
                    listed_price = get_listed_price(position.item, position.variation, position.subevent)
                    if not position.item.tax_rule or position.item.tax_rule.price_includes_tax:
                        price_after_voucher = max(position.price, position.voucher.calculate_price(listed_price))
                    else:
                        price_after_voucher = max(position.price - position.tax_value, position.voucher.calculate_price(listed_price))
                    position.voucher_budget_use = max(listed_price - price_after_voucher, Decimal('0.00'))
                position.save()
            elif isinstance(op, self.AddFeeOperation):
                self.order.log_action('pretix.event.order.changed.addfee', user=self.user, auth=self.auth, data={
                    'fee': op.fee.pk,
                })
                op.fee.order = self.order
                op.fee._calculate_tax()
                op.fee.save()
            elif isinstance(op, self.FeeValueOperation):
                fee = fee_cache.setdefault(op.fee.pk, op.fee)
                self.order.log_action('pretix.event.order.changed.feevalue', user=self.user, auth=self.auth, data={
                    'fee': fee.pk,
                    'old_price': fee.value,
                    'new_price': op.value.gross
                })
                fee.value = op.value.gross
                fee._calculate_tax()
                fee.save()
            elif isinstance(op, self.PriceOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.price', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'old_price': position.price,
                    'addon_to': position.addon_to_id,
                    'new_price': op.price.gross
                })
                position.price = op.price.gross
                position.price_includes_rounding_correction = Decimal("0.00")
                position.tax_rate = op.price.rate
                position.tax_value = op.price.tax
                position.tax_value_includes_rounding_correction = Decimal("0.00")
                position.tax_code = op.price.code
                position.save(update_fields=[
                    'price', 'price_includes_rounding_correction', 'tax_rate', 'tax_value',
                    'tax_value_includes_rounding_correction', 'tax_code'
                ])
            elif isinstance(op, self.TaxRuleOperation):
                if isinstance(op.position, OrderPosition):
                    position = position_cache.setdefault(op.position.pk, op.position)
                    self.order.log_action('pretix.event.order.changed.tax_rule', user=self.user, auth=self.auth, data={
                        'position': position.pk,
                        'positionid': position.positionid,
                        'addon_to': position.addon_to_id,
                        'old_taxrule': position.tax_rule.pk if position.tax_rule else None,
                        'new_taxrule': op.tax_rule.pk
                    })
                    position._calculate_tax(op.tax_rule)
                    position.save()
                elif isinstance(op.position, OrderFee):
                    fee = fee_cache.setdefault(op.position.pk, op.position)
                    self.order.log_action('pretix.event.order.changed.tax_rule', user=self.user, auth=self.auth, data={
                        'fee': fee.pk,
                        'fee_type': fee.fee_type,
                        'old_taxrule': fee.tax_rule.pk if fee.tax_rule else None,
                        'new_taxrule': op.tax_rule.pk
                    })
                    fee._calculate_tax(op.tax_rule)
                    fee.save()
            elif isinstance(op, self.CancelFeeOperation):
                fee = fee_cache.setdefault(op.fee.pk, op.fee)
                self.order.log_action('pretix.event.order.changed.cancelfee', user=self.user, auth=self.auth, data={
                    'fee': fee.pk,
                    'fee_type': fee.fee_type,
                    'old_price': fee.value,
                })
                fee.canceled = True
                fee.save(update_fields=['canceled'])
            elif isinstance(op, self.CancelOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                for gc in position.issued_gift_cards.all():
                    gc = GiftCard.objects.select_for_update(of=OF_SELF).get(pk=gc.pk)
                    if gc.value < position.price:
                        raise OrderError(_(
                            'A position can not be canceled since the gift card {card} purchased in this order has '
                            'already been redeemed.').format(
                            card=gc.secret
                        ))
                    else:
                        gc.transactions.create(value=-position.price, order=self.order, acceptor=self.order.event.organizer)
                        gc.log_action(
                            action='pretix.giftcards.transaction.manual',
                            user=self.user,
                            auth=self.auth,
                            data={
                                'value': -position.price,
                                'acceptor_id': self.order.event.organizer.id
                            }
                        )

                for m in position.granted_memberships.with_usages().all():
                    m.canceled = True
                    m.save()

                for opa in position.addons.all():
                    opa = position_cache.setdefault(opa.pk, opa)
                    for gc in opa.issued_gift_cards.all():
                        gc = GiftCard.objects.select_for_update(of=OF_SELF).get(pk=gc.pk)
                        if gc.value < opa.position.price:
                            raise OrderError(_(
                                'A position can not be canceled since the gift card {card} purchased in this order has '
                                'already been redeemed.').format(
                                card=gc.secret
                            ))
                        else:
                            gc.transactions.create(value=-opa.position.price, order=self.order, acceptor=self.order.event.organizer)
                            gc.log_action(
                                action='pretix.giftcards.transaction.manual',
                                user=self.user,
                                auth=self.auth,
                                data={
                                    'value': -opa.position.price,
                                    'acceptor_id': self.order.event.organizer.id
                                }
                            )

                    for m in opa.granted_memberships.with_usages().all():
                        m.canceled = True
                        m.save()

                    self.order.log_action('pretix.event.order.changed.cancel', user=self.user, auth=self.auth, data={
                        'position': opa.pk,
                        'positionid': opa.positionid,
                        'old_item': opa.item.pk,
                        'old_variation': opa.variation.pk if opa.variation else None,
                        'addon_to': opa.addon_to_id,
                        'old_price': opa.price,
                    })
                    opa.canceled = True
                    if opa.voucher:
                        Voucher.objects.filter(pk=opa.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))
                    if opa in secret_dirty:
                        secret_dirty.remove(opa)
                    assign_ticket_secret(
                        event=self.event, position=opa, force_invalidate_if_revokation_list_used=True, force_invalidate=False, save=False
                    )
                    opa.save(update_fields=['canceled', 'secret'])
                self.order.log_action('pretix.event.order.changed.cancel', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'old_item': position.item.pk,
                    'old_variation': position.variation.pk if position.variation else None,
                    'old_price': position.price,
                    'addon_to': None,
                })
                position.canceled = True
                if position.voucher:
                    Voucher.objects.filter(pk=position.voucher.pk).update(redeemed=Greatest(0, F('redeemed') - 1))
                assign_ticket_secret(
                    event=self.event, position=position, force_invalidate_if_revokation_list_used=True, force_invalidate=False, save=False
                )
                if position in secret_dirty:
                    secret_dirty.remove(position)
                position.save(update_fields=['canceled', 'secret'])
            elif isinstance(op, self.AddOperation):
                pos = OrderPosition.objects.create(
                    item=op.item, variation=op.variation, addon_to=op.addon_to,
                    price=op.price.gross, order=self.order, tax_rate=op.price.rate, tax_code=op.price.code,
                    tax_value=op.price.tax, tax_rule=op.item.tax_rule,
                    positionid=nextposid, subevent=op.subevent, seat=op.seat,
                    used_membership=op.membership, valid_from=op.valid_from, valid_until=op.valid_until,
                    is_bundled=op.is_bundled,
                )
                nextposid += 1
                self.order.log_action('pretix.event.order.changed.add', user=self.user, auth=self.auth, data={
                    'position': pos.pk,
                    'item': op.item.pk,
                    'variation': op.variation.pk if op.variation else None,
                    'addon_to': op.addon_to.pk if op.addon_to else None,
                    'price': op.price.gross,
                    'positionid': pos.positionid,
                    'membership': pos.used_membership_id,
                    'subevent': op.subevent.pk if op.subevent else None,
                    'seat': op.seat.pk if op.seat else None,
                    'valid_from': op.valid_from.isoformat() if op.valid_from else None,
                    'valid_until': op.valid_until.isoformat() if op.valid_until else None,
                })
                op.result._position = pos
            elif isinstance(op, self.SplitOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                split_positions.append(position)
            elif isinstance(op, self.RegenerateSecretOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                position.web_secret = generate_secret()
                position.save(update_fields=["web_secret"])
                assign_ticket_secret(
                    event=self.event, position=position, force_invalidate=True, save=True
                )
                if position in secret_dirty:
                    secret_dirty.remove(position)
                tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk,
                                                             'order': self.order.pk})
                self.order.log_action('pretix.event.order.changed.secret', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                })
            elif isinstance(op, self.ChangeSecretOperation):
                if OrderPosition.all.filter(order__event=self.event, secret=op.new_secret).exists():
                    raise OrderError('You cannot assign a position secret that already exists.')
                op.position.secret = op.new_secret
                op.position.save(update_fields=["secret"])
                if op.position in secret_dirty:
                    secret_dirty.remove(op.position)
                tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk,
                                                             'order': self.order.pk})
                self.order.log_action('pretix.event.order.changed.secret', user=self.user, auth=self.auth, data={
                    'position': op.position.pk,
                    'positionid': op.position.positionid,
                })
            elif isinstance(op, self.ChangeValidFromOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.valid_from', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'new_value': op.valid_from.isoformat() if op.valid_from else None,
                    'old_value': position.valid_from.isoformat() if position.valid_from else None,
                })
                position.valid_from = op.valid_from
                position.save(update_fields=['valid_from'])
                secret_dirty.add(position)
            elif isinstance(op, self.ChangeValidUntilOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.valid_until', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'new_value': op.valid_until.isoformat() if op.valid_until else None,
                    'old_value': position.valid_until.isoformat() if position.valid_until else None,
                })
                position.valid_until = op.valid_until
                position.save(update_fields=['valid_until'])
                secret_dirty.add(position)
            elif isinstance(op, self.AddBlockOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.add_block', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'block_name': op.block_name,
                })
                if position.blocked:
                    if op.block_name not in position.blocked:
                        position.blocked = position.blocked + [op.block_name]
                else:
                    position.blocked = [op.block_name]
                if op.ignore_from_quota_while_blocked is not None:
                    position.ignore_from_quota_while_blocked = op.ignore_from_quota_while_blocked
                position.save(update_fields=['blocked', 'ignore_from_quota_while_blocked'])
                if position.blocked:
                    position.blocked_secrets.update_or_create(
                        event=self.event,
                        secret=position.secret,
                        defaults={
                            'blocked': True,
                            'updated': now(),
                        }
                    )
            elif isinstance(op, self.RemoveBlockOperation):
                position = position_cache.setdefault(op.position.pk, op.position)
                self.order.log_action('pretix.event.order.changed.remove_block', user=self.user, auth=self.auth, data={
                    'position': position.pk,
                    'positionid': position.positionid,
                    'block_name': op.block_name,
                })
                if position.blocked and op.block_name in position.blocked:
                    position.blocked = [b for b in position.blocked if b != op.block_name]
                    if not position.blocked:
                        position.blocked = None
                    if op.ignore_from_quota_while_blocked is not None:
                        position.ignore_from_quota_while_blocked = op.ignore_from_quota_while_blocked
                    position.save(update_fields=['blocked', 'ignore_from_quota_while_blocked'])
                    if not position.blocked:
                        try:
                            bs = position.blocked_secrets.get(secret=position.secret)
                            bs.blocked = False
                            bs.save()
                        except BlockedTicketSecret.DoesNotExist:
                            pass
                # todo: revoke list handling
            elif isinstance(op, self.ForceRecomputeOperation):
                self.order.log_action('pretix.event.order.changed.recomputed', user=self.user, auth=self.auth, data={})
            else:
                raise TypeError(f"Unknown operation {type(op)}")

        for p in secret_dirty:
            assign_ticket_secret(
                event=self.event, position=p, force_invalidate=False, save=True
            )

        if split_positions:
            self.split_order = self._create_split_order(split_positions)

    def _create_split_order(self, split_positions):
        split_order = Order.objects.get(pk=self.order.pk)
        split_order.pk = None
        split_order.code = None
        split_order.datetime = now()
        split_order.secret = generate_secret()
        split_order.require_approval = self.order.require_approval and any(p.requires_approval(invoice_address=self._invoice_address) for p in split_positions)
        split_order.save()
        split_order.log_action('pretix.event.order.changed.split_from', user=self.user, auth=self.auth, data={
            'original_order': self.order.code
        })

        for op in split_positions:
            self.order.log_action('pretix.event.order.changed.split', user=self.user, auth=self.auth, data={
                'position': op.pk,
                'positionid': op.positionid,
                'old_item': op.item.pk,
                'old_variation': op.variation.pk if op.variation else None,
                'old_price': op.price,
                'new_order': split_order.code,
            })
            op.order = split_order
            op.web_secret = generate_secret()
            assign_ticket_secret(
                self.event, position=op, force_invalidate=True,
            )
            op.save()

        try:
            ia = modelcopy(self.order.invoice_address)
            ia.pk = None
            ia.order = split_order
            ia.save()
        except InvoiceAddress.DoesNotExist:
            pass

        fees = []
        for fee in self.order.fees.exclude(fee_type=OrderFee.FEE_TYPE_PAYMENT):
            new_fee = modelcopy(fee)
            new_fee.pk = None
            new_fee.order = split_order
            new_fee.save()
            fees.append(new_fee)

        changed_by_rounding = set(apply_rounding(
            self.order.tax_rounding_mode,
            self._invoice_address,
            self.event.currency,
            [p for p in split_positions if not p.canceled] + fees
        ))
        split_order.total = sum([p.price for p in split_positions if not p.canceled])

        if split_order.total != Decimal('0.00') and self.order.status != Order.STATUS_PAID:
            pp = self._get_payment_provider()
            if pp:
                payment_fee = pp.calculate_fee(split_order.total)
            else:
                payment_fee = Decimal('0.00')
            fee = split_order.fees.get_or_create(fee_type=OrderFee.FEE_TYPE_PAYMENT, defaults={'value': 0})[0]
            fee.value = payment_fee
            fee._calculate_tax()
            if payment_fee != 0:
                fee.save()
                fees.append(fee)
            elif fee.pk:
                if fee in fees:
                    fees.remove(fee)
                fee.delete()

            changed_by_rounding |= set(apply_rounding(
                self.order.tax_rounding_mode,
                self._invoice_address,
                self.event.currency,
                [p for p in split_positions if not p.canceled] + fees
            ))
            split_order.total = sum([p.price for p in split_positions if not p.canceled]) + sum([f.value for f in fees])

        for l in changed_by_rounding:
            if isinstance(l, OrderPosition):
                l.save(update_fields=[
                    "price", "price_includes_rounding_correction", "tax_value", "tax_value_includes_rounding_correction"
                ])
            elif isinstance(l, OrderFee):
                l.save(update_fields=[
                    "value", "value_includes_rounding_correction", "tax_value", "tax_value_includes_rounding_correction"
                ])
        split_order.total = sum([p.price for p in split_positions if not p.canceled]) + sum([f.value for f in fees])

        remaining_total = sum([p.price for p in self.order.positions.all()]) + sum([f.value for f in self.order.fees.all()])
        offset_amount = min(max(0, self.completed_payment_sum - remaining_total), split_order.total)
        if offset_amount >= split_order.total and not split_order.require_approval:
            split_order.status = Order.STATUS_PAID
        else:
            split_order.status = Order.STATUS_PENDING
            if self.order.status == Order.STATUS_PAID:
                split_order.set_expires(
                    now(),
                    list(set(p.subevent_id for p in split_positions))
                )
        split_order.save()

        if offset_amount > Decimal('0.00'):
            split_order.payments.create(
                state=OrderPayment.PAYMENT_STATE_CONFIRMED,
                amount=offset_amount,
                payment_date=now(),
                provider='offsetting',
                info=json.dumps({'orders': [self.order.code]})
            )
            self.order.refunds.create(
                state=OrderRefund.REFUND_STATE_DONE,
                amount=offset_amount,
                execution_date=now(),
                provider='offsetting',
                info=json.dumps({'orders': [split_order.code]})
            )

        if split_order.total != Decimal('0.00') and self.order.invoices.filter(is_cancellation=False).last():
            try:
                generate_invoice(split_order)
            except Exception as e:
                logger.exception("Could not generate invoice.")
                split_order.log_action("pretix.event.order.invoice.failed", data={
                    "exception": str(e)
                })

        order_split.send(sender=self.order.event, original=self.order, split_order=split_order)
        return split_order

    @cached_property
    def open_payment(self):
        lp = self.order.payments.last()
        if lp and lp.state not in (OrderPayment.PAYMENT_STATE_CONFIRMED,
                                   OrderPayment.PAYMENT_STATE_REFUNDED):
            return lp

    @cached_property
    def completed_payment_sum(self):
        payment_sum = self.order.payments.filter(
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        refund_sum = self.order.refunds.filter(
            state__in=(OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_TRANSIT, OrderRefund.REFUND_STATE_DONE)
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        return payment_sum - refund_sum

    def _recalculate_rounding_total_and_payment_fee(self):
        positions = list(self.order.positions.all())
        fees = list(self.order.fees.all())
        total = sum([p.price for p in positions]) + sum([f.value for f in fees])
        payment_fee = Decimal('0.00')
        fee_changed = False
        if self.open_payment:
            current_fee = Decimal('0.00')
            fee = None
            if self.open_payment.fee:
                fee = self.open_payment.fee
                if any(isinstance(op, (self.FeeValueOperation, self.CancelFeeOperation)) for op in self._operations):
                    fee.refresh_from_db()
                if not self.open_payment.fee.canceled:
                    current_fee = self.open_payment.fee.value
            total -= current_fee

            if fee and any([isinstance(op, self.FeeValueOperation) and op.fee == fee for op in self._operations]):
                # Do not automatically modify a fee that is being manually modified right now
                payment_fee = fee.value
            elif fee and any([isinstance(op, self.CancelFeeOperation) and op.fee == fee for op in self._operations]):
                # Do not automatically modify a fee that is being manually removed right now
                payment_fee = Decimal('0.00')
            elif self.order.pending_sum - current_fee != 0:
                prov = self.open_payment.payment_provider
                if prov:
                    payment_fee = prov.calculate_fee(total - self.completed_payment_sum)

            if payment_fee:
                fee = fee or OrderFee(fee_type=OrderFee.FEE_TYPE_PAYMENT, order=self.order)
                fee.value = payment_fee
                fee._calculate_tax()
                fee.save()
                fee_changed = True
                if not self.open_payment.fee:
                    self.open_payment.fee = fee
                    self.open_payment.save(update_fields=['fee'])
            elif fee and not fee.canceled:
                fee.delete()
                fee_changed = True

        if fee_changed:
            fees = list(self.order.fees.all())

        changed = apply_rounding(
            self.order.tax_rounding_mode,
            self._invoice_address,
            self.order.event.currency,
            [*positions, *fees]
        )
        for l in changed:
            if isinstance(l, OrderPosition):
                l.save(update_fields=[
                    "price", "price_includes_rounding_correction", "tax_value", "tax_value_includes_rounding_correction"
                ])
            elif isinstance(l, OrderFee):
                l.save(update_fields=[
                    "value", "value_includes_rounding_correction", "tax_value", "tax_value_includes_rounding_correction"
                ])
        total = sum([p.price for p in positions]) + sum([f.value for f in fees])

        self.order.total = total
        self.order.save()
        return total

    def _check_order_size(self):
        if (len(self.order.positions.all()) + len([op for op in self._operations if isinstance(op, self.AddOperation)])) > settings.PRETIX_MAX_ORDER_SIZE:
            raise OrderError(
                self.error_messages['max_order_size'] % {
                    'max': settings.PRETIX_MAX_ORDER_SIZE,
                }
            )

    def _reissue_invoice(self):
        i = self.order.invoices.filter(is_cancellation=False).last()
        if self.reissue_invoice and self._invoice_dirty:
            order_now_qualified = invoice_qualified(self.order)
            invoice_should_be_generated_now = (
                self.event.settings.invoice_generate == "True" or (
                    self.event.settings.invoice_generate == "paid" and
                    self.open_payment is not None and
                    self.open_payment.payment_provider.requires_invoice_immediately
                ) or (
                    self.event.settings.invoice_generate == "paid" and
                    self.order.status == Order.STATUS_PAID
                ) or (
                    # Backwards-compatible behaviour
                    self.event.settings.invoice_generate not in ("True", "paid") and
                    i and
                    not i.canceled
                )
            )
            invoice_should_be_generated_later = not invoice_should_be_generated_now and (
                self.event.settings.invoice_generate in ("True", "paid")
            )

            if order_now_qualified:
                if invoice_should_be_generated_now:
                    try:
                        if i and not i.canceled:
                            self._invoices.append(generate_cancellation(i))
                        self._invoices.append(generate_invoice(self.order))
                    except Exception as e:
                        logger.exception("Could not generate invoice.")
                        self.order.log_action("pretix.event.order.invoice.failed", data={
                            "exception": str(e)
                        })
                elif invoice_should_be_generated_later:
                    self.order.invoice_dirty = True
                    self.order.save(update_fields=["invoice_dirty"])
            else:
                try:
                    if i and not i.canceled:
                        self._invoices.append(generate_cancellation(i))
                except Exception as e:
                    logger.exception("Could not generate invoice.")
                    self.order.log_action("pretix.event.order.invoice.failed", data={
                        "exception": str(e)
                    })

    def _check_complete_cancel(self):
        current = self.order.positions.count()
        cancels = sum([
            1 + o.position.addons.filter(canceled=False).count() for o in self._operations if isinstance(o, self.CancelOperation)
        ]) + len([
            o for o in self._operations if isinstance(o, self.SplitOperation)
        ])
        adds = len([o for o in self._operations if isinstance(o, self.AddOperation)])
        if current > 0 and current - cancels + adds < 1:
            raise OrderError(self.error_messages['complete_cancel'])

    @property
    def _invoice_address(self):
        try:
            return self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            return None

    def _check_and_lock_memberships(self):
        # To avoid duplicating all the logic around memberships, we simulate an application of all relevant
        # operations in a non-existing cart and then pass that to our cart checker.
        fake_cart = []
        positions_to_fake_cart = {}

        for p in self.order.positions.all():
            cp = CartPosition(
                event=self.event,
                item=p.item,
                variation=p.variation,
                attendee_name_parts=p.attendee_name_parts,
                used_membership=p.used_membership,
                subevent=p.subevent,
                seat=p.seat,
            )
            fake_cart.append(cp)
            positions_to_fake_cart[p] = cp

        for op in self._operations:
            if isinstance(op, self.ItemOperation):
                positions_to_fake_cart[op.position].item = op.item
                positions_to_fake_cart[op.position].variation = op.variation
            elif isinstance(op, self.SubeventOperation):
                positions_to_fake_cart[op.position].subevent = op.subevent
            elif isinstance(op, self.SeatOperation):
                positions_to_fake_cart[op.position].seat = op.seat
            elif isinstance(op, self.MembershipOperation):
                positions_to_fake_cart[op.position].used_membership = op.membership
            elif isinstance(op, self.ChangeValidFromOperation):
                positions_to_fake_cart[op.position].override_valid_from = op.valid_from
            elif isinstance(op, self.ChangeValidUntilOperation):
                positions_to_fake_cart[op.position].override_valid_until = op.valid_until
            elif isinstance(op, self.CancelOperation) and op.position in positions_to_fake_cart:
                fake_cart.remove(positions_to_fake_cart[op.position])
            elif isinstance(op, self.AddOperation):
                cp = CartPosition(
                    event=self.event,
                    item=op.item,
                    variation=op.variation,
                    used_membership=op.membership,
                    subevent=op.subevent,
                    seat=op.seat,
                )
                cp.override_valid_from = op.valid_from
                cp.override_valid_until = op.valid_until
                fake_cart.append(cp)
        try:
            validate_memberships_in_order(self.order.customer, fake_cart, self.event, lock=True, ignored_order=self.order, testmode=self.order.testmode)
        except ValidationError as e:
            raise OrderError(e.message)

    def _create_locks(self):
        full_lock_required = any(diff > 0 for diff in self._seatdiff.values()) and self.event.settings.seating_minimal_distance > 0
        if full_lock_required:
            # We lock the entire event in this case since we don't want to deal with fine-granular locking
            # in the case of seating distance enforcement
            lock_objects([self.event])
        else:
            lock_objects(
                [q for q, d in self._quotadiff.items() if q.size is not None and d > 0] +
                [s for s, d in self._seatdiff.items() if d > 0],
                shared_lock_objects=[self.event]
            )

    def guess_totaldiff(self):
        """
        Return the estimated difference of ``order.total`` based on the currently queued operations. This is only
        a guess since it does not account for (a) tax rounding or (b) payment fee changes.
        """
        return self._totaldiff_guesstimate

    def commit(self, check_quotas=True):
        if self._committed:
            # an order change can only be committed once
            raise OrderError(error_messages['internal'])
        self._committed = True

        if not self._operations:
            # Do nothing
            return

        # Clear prefetched objects cache of order. We're going to modify the positions and fees and we have no guarantee
        # that every operation tuple points to a position/fee instance that has been fetched from the same object cache,
        # so it's dangerous to keep the cache around.
        self.order._prefetched_objects_cache = {}

        self._check_order_size()

        with transaction.atomic():
            locked_instance = Order.objects.select_for_update(of=OF_SELF).get(pk=self.order.pk)
            if locked_instance.last_modified != self.order.last_modified:
                raise OrderError(error_messages['race_condition'])

            original_total = self.order.total
            if self.order.status in (Order.STATUS_PENDING, Order.STATUS_PAID):
                if check_quotas:
                    self._check_quotas()
                self._check_seats()
            self._create_locks()
            self._check_complete_cancel()
            self._check_and_lock_memberships()
            try:
                self._perform_operations()
            except TaxRule.SaleNotAllowed:
                raise OrderError(self.error_messages['tax_rule_country_blocked'])
            new_total = self._recalculate_rounding_total_and_payment_fee()
            totaldiff = new_total - original_total
            self._check_paid_price_change(totaldiff)
            self._check_paid_to_free(totaldiff)
            if self.order.status in (Order.STATUS_PENDING, Order.STATUS_PAID):
                self._reissue_invoice()
            self._clear_tickets_cache()
            self.order.touch()
            self.order.create_transactions()
            if self.split_order:
                self.split_order.create_transactions()

        transmit_invoices_task = [i for i in self._invoices if invoice_transmission_separately(i)]
        transmit_invoices_mail = [
            i for i in self._invoices
            if i not in transmit_invoices_task and self.event.settings.invoice_email_attachment and self.order.email
        ]

        if self.split_order:
            split_invoices = list(self.split_order.invoices.all())
            transmit_invoices_task += [
                i for i in split_invoices if invoice_transmission_separately(i)
            ]
            split_transmit_invoices_mail = [
                i for i in split_invoices
                if i not in transmit_invoices_task and self.event.settings.invoice_email_attachment and self.order.email
            ]

        if self.notify:
            notify_user_changed_order(
                self.order, self.user, self.auth,
                transmit_invoices_mail,
            )
            if self.split_order:
                notify_user_changed_order(
                    self.split_order, self.user, self.auth,
                    split_transmit_invoices_mail,
                )

        for i in transmit_invoices_task:
            transmit_invoice.apply_async(args=(self.event.pk, i.pk, False))

        order_changed.send(self.order.event, order=self.order)

    def _clear_tickets_cache(self):
        tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk,
                                                     'order': self.order.pk})
        if self.split_order:
            tickets.invalidate_cache.apply_async(kwargs={'event': self.event.pk,
                                                         'order': self.split_order.pk})

    def _get_payment_provider(self):
        lp = self.order.payments.last()
        if not lp:
            return None
        pprov = lp.payment_provider
        if not pprov:
            return None
        return pprov


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
def perform_order(self, event: Event, payments: List[dict], positions: List[str],
                  email: str=None, locale: str=None, address: int=None, meta_info: dict=None,
                  sales_channel: str='web', shown_total=None, customer=None, override_now_dt: datetime=None,
                  api_meta: dict=None):
    with language(locale), time_machine_now_assigned(override_now_dt):
        try:
            try:
                return _perform_order(event, payments, positions, email, locale, address, meta_info,
                                      sales_channel, shown_total, customer, api_meta)
            except LockTimeoutException:
                self.retry()
        except (MaxRetriesExceededError, LockTimeoutException):
            raise OrderError(error_messages['busy'])


_unset = object()


def _try_auto_refund(order, auto_refund=True, manual_refund=False, allow_partial=False,
                     source=OrderRefund.REFUND_SOURCE_BUYER,
                     refund_as_giftcard=False, giftcard_expires=_unset, giftcard_conditions=None, comment=None):
    notify_admin = False
    error = False
    if isinstance(order, int):
        order = Order.objects.get(pk=order)
    refund_amount = order.pending_sum * -1
    if refund_amount <= Decimal('0.00'):
        return

    can_auto_refund_sum = 0

    if refund_as_giftcard:
        can_auto_refund_sum = refund_amount
        with transaction.atomic():
            giftcard = order.event.organizer.issued_gift_cards.create(
                expires=order.event.organizer.default_gift_card_expiry if giftcard_expires is _unset else giftcard_expires,
                conditions=giftcard_conditions,
                currency=order.event.currency,
                customer=order.customer,
                testmode=order.testmode
            )
            giftcard.log_action(
                action='pretix.giftcards.created',
                data={}
            )
            r = order.refunds.create(
                order=order,
                payment=None,
                source=source,
                comment=comment,
                state=OrderRefund.REFUND_STATE_CREATED,
                execution_date=now(),
                amount=can_auto_refund_sum,
                provider='giftcard',
                info=json.dumps({
                    'gift_card': giftcard.pk
                })
            )
            try:
                r.payment_provider.execute_refund(r)
            except PaymentException as e:
                with transaction.atomic():
                    r.state = OrderRefund.REFUND_STATE_FAILED
                    r.save()
                    order.log_action('pretix.event.order.refund.failed', {
                        'local_id': r.local_id,
                        'provider': r.provider,
                        'error': str(e)
                    })
                error = True
                notify_admin = True
            else:
                if r.state != OrderRefund.REFUND_STATE_DONE:
                    notify_admin = True

    elif auto_refund:
        proposals = order.propose_auto_refunds(refund_amount)
        can_auto_refund_sum = sum(proposals.values())
        if (allow_partial and can_auto_refund_sum) or can_auto_refund_sum == refund_amount:
            for p, value in proposals.items():
                with transaction.atomic():
                    r = order.refunds.create(
                        payment=p,
                        source=source,
                        state=OrderRefund.REFUND_STATE_CREATED,
                        amount=value,
                        comment=comment,
                        provider=p.provider
                    )
                    order.log_action('pretix.event.order.refund.created', {
                        'local_id': r.local_id,
                        'provider': r.provider,
                    })

                try:
                    r.payment_provider.execute_refund(r)
                except PaymentException as e:
                    with transaction.atomic():
                        r.state = OrderRefund.REFUND_STATE_FAILED
                        r.save()
                        order.log_action('pretix.event.order.refund.failed', {
                            'local_id': r.local_id,
                            'provider': r.provider,
                            'error': str(e)
                        })
                    error = True
                    notify_admin = True
                else:
                    if r.state not in (OrderRefund.REFUND_STATE_TRANSIT, OrderRefund.REFUND_STATE_DONE):
                        notify_admin = True

    if refund_amount - can_auto_refund_sum > Decimal('0.00'):
        if manual_refund:
            with transaction.atomic():
                r = order.refunds.create(
                    source=source,
                    comment=comment,
                    state=OrderRefund.REFUND_STATE_CREATED,
                    amount=refund_amount - can_auto_refund_sum,
                    provider='manual'
                )
                order.log_action('pretix.event.order.refund.created', {
                    'local_id': r.local_id,
                    'provider': r.provider,
                })
        else:
            notify_admin = True

    if notify_admin:
        order.log_action('pretix.event.order.refund.requested')
    if error:
        raise OrderError(
            _(
                'There was an error while trying to send the money back to you. Please contact the event organizer '
                'for further information.')
        )


@app.task(base=ProfiledTask, bind=True, max_retries=5, default_retry_delay=1, throws=(OrderError,))
@scopes_disabled()
def cancel_order(self, order: int, user: int=None, send_mail: bool=True, api_token=None, oauth_application=None,
                 device=None, cancellation_fee=None, try_auto_refund=False, refund_as_giftcard=False,
                 email_comment=None, refund_comment=None, cancel_invoice=True):
    try:
        try:
            ret = _cancel_order(order, user, send_mail, api_token, device, oauth_application,
                                cancellation_fee, cancel_invoice=cancel_invoice, comment=email_comment)
            if try_auto_refund:
                _try_auto_refund(order, refund_as_giftcard=refund_as_giftcard,
                                 comment=refund_comment)
            return ret
        except LockTimeoutException:
            self.retry()
    except (MaxRetriesExceededError, LockTimeoutException):
        raise OrderError(error_messages['busy'])


def change_payment_provider(order: Order, payment_provider, amount=None, new_payment=None, create_log=True,
                            recreate_invoices=True):
    if not get_connection().in_atomic_block:
        raise Exception('change_payment_provider should only be called in atomic transaction!')

    oldtotal = order.total
    already_paid = order.payment_refund_sum
    e = OrderPayment.objects.filter(fee=OuterRef('pk'), state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED,
                                                                   OrderPayment.PAYMENT_STATE_REFUNDED))
    open_fees = list(
        order.fees.annotate(has_p=Exists(e)).filter(
            Q(fee_type=OrderFee.FEE_TYPE_PAYMENT) & ~Q(has_p=True)
        )
    )
    if open_fees:
        fee = open_fees[0]
        if len(open_fees) > 1:
            for f in open_fees[1:]:
                f.delete()
    else:
        fee = OrderFee(fee_type=OrderFee.FEE_TYPE_PAYMENT, value=Decimal('0.00'), order=order)
    old_fee = fee.value

    positions = list(order.positions.all())
    fees = list(order.fees.all())
    try:
        ia = order.invoice_address
    except InvoiceAddress.DoesNotExist:
        ia = None
    rounding_changed = set(apply_rounding(
        order.tax_rounding_mode, ia, order.event.currency, [*positions, *[f for f in fees if f.pk != fee.pk]]
    ))
    total_without_fee = sum(c.price for c in positions) + sum(f.value for f in fees if f.pk != fee.pk)
    pending_sum_without_fee = max(Decimal("0.00"), total_without_fee - already_paid)

    new_fee = payment_provider.calculate_fee(
        pending_sum_without_fee if amount is None else amount
    )
    if new_fee:
        fee.value = new_fee
        fee.internal_type = payment_provider.identifier
        fee._calculate_tax()
        if fee in fees:
            fees.remove(fee)
        # "Update instance in the fees array
        fees.append(fee)
        fee.save()
    else:
        if fee in fees:
            fees.remove(fee)
        if fee.pk:
            fee.delete()
        fee = None

    rounding_changed |= set(apply_rounding(
        order.tax_rounding_mode, ia, order.event.currency, [*positions, *fees]
    ))
    for l in rounding_changed:
        if isinstance(l, OrderPosition):
            l.save(update_fields=[
                "price", "price_includes_rounding_correction", "tax_value", "tax_value_includes_rounding_correction"
            ])
        elif isinstance(l, OrderFee):
            l.save(update_fields=[
                "value", "value_includes_rounding_correction", "tax_value", "tax_value_includes_rounding_correction"
            ])

    open_payment = None
    if new_payment:
        lp = order.payments.select_for_update(of=OF_SELF).exclude(pk=new_payment.pk).last()
    else:
        lp = order.payments.select_for_update(of=OF_SELF).last()

    if lp and lp.state in (OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED):
        open_payment = lp

    if open_payment:
        try:
            open_payment.payment_provider.cancel_payment(open_payment)
            order.log_action('pretix.event.order.payment.canceled', {
                'local_id': open_payment.local_id,
                'provider': open_payment.provider,
            })
        except PaymentException as e:
            order.log_action(
                'pretix.event.order.payment.canceled.failed',
                {
                    'local_id': open_payment.local_id,
                    'provider': open_payment.provider,
                    'error': str(e)
                },
            )

    order.total = sum(c.price for c in positions) + sum(f.value for f in fees)
    order.save(update_fields=['total'])

    if not new_payment:
        new_payment = order.payments.create(
            state=OrderPayment.PAYMENT_STATE_CREATED,
            provider=payment_provider.identifier,
            amount=order.pending_sum,
            fee=fee
        )
    if create_log and new_payment:
        order.log_action(
            'pretix.event.order.payment.changed' if open_payment else 'pretix.event.order.payment.started',
            {
                'fee': new_fee,
                'old_fee': old_fee,
                'provider': payment_provider.identifier,
                'payment': new_payment.pk,
                'local_id': new_payment.local_id,
            }
        )

    new_invoice_created = False
    if recreate_invoices:
        # Lock to prevent duplicate invoice creation
        order = Order.objects.select_for_update(of=OF_SELF).get(pk=order.pk)

        i = order.invoices.filter(is_cancellation=False).last()
        has_active_invoice = i and not i.canceled

        if has_active_invoice and order.total != oldtotal:
            try:
                generate_cancellation(i)
                generate_invoice(order)
            except Exception as e:
                logger.exception("Could not generate invoice.")
                order.log_action("pretix.event.order.invoice.failed", data={
                    "exception": str(e)
                })
            new_invoice_created = True

        elif (not has_active_invoice or order.invoice_dirty) and invoice_qualified(order):
            if order.event.settings.get('invoice_generate') == 'True' or (
                order.event.settings.get('invoice_generate') == 'paid' and
                new_payment.payment_provider.requires_invoice_immediately
            ):
                try:
                    if has_active_invoice:
                        generate_cancellation(i)
                    i = generate_invoice(order)
                    new_invoice_created = True
                    order.log_action('pretix.event.order.invoice.generated', data={
                        'invoice': i.pk
                    })
                except Exception as e:
                    logger.exception("Could not generate invoice.")
                    order.log_action("pretix.event.order.invoice.failed", data={
                        "exception": str(e)
                    })

    order.create_transactions()
    return old_fee, new_fee, fee, new_payment, new_invoice_created


@receiver(order_paid, dispatch_uid="pretixbase_order_paid_giftcards")
@receiver(order_changed, dispatch_uid="pretixbase_order_changed_giftcards")
@transaction.atomic()
def signal_listener_issue_giftcards(sender: Event, order: Order, **kwargs):
    if order.status != Order.STATUS_PAID:
        return
    any_giftcards = False
    for p in order.positions.all():
        if p.item.issue_giftcard:
            issued = Decimal('0.00')
            for gc in p.issued_gift_cards.all():
                issued += gc.transactions.first().value
            if p.price - issued > 0:
                gc = sender.organizer.issued_gift_cards.create(
                    currency=sender.currency, issued_in=p, testmode=order.testmode,
                    expires=sender.organizer.default_gift_card_expiry,
                )
                gc.log_action(
                    action='pretix.giftcards.created',
                )
                trans = gc.transactions.create(value=p.price - issued, order=order, acceptor=sender.organizer)
                gc.log_action(
                    action='pretix.giftcards.transaction.manual',
                    data={
                        'value': trans.value,
                        'acceptor_id': order.event.organizer.id,
                    }
                )
                any_giftcards = True
                p.secret = gc.secret
                p.save(update_fields=['secret'])

    if any_giftcards:
        tickets.invalidate_cache.apply_async(kwargs={'event': sender.pk, 'order': order.pk})


@receiver(order_paid, dispatch_uid="pretixbase_order_paid_memberships")
@receiver(order_changed, dispatch_uid="pretixbase_order_changed_memberships")
@transaction.atomic()
def signal_listener_issue_memberships(sender: Event, order: Order, **kwargs):
    if order.status != Order.STATUS_PAID or not order.customer:
        return
    for p in order.positions.all():
        if p.item.grant_membership_type_id and not p.granted_memberships.exists():
            create_membership(order.customer, p)


@receiver(order_placed, dispatch_uid="pretixbase_order_placed_media")
@receiver(order_changed, dispatch_uid="pretixbase_order_changed_media")
@transaction.atomic()
def signal_listener_issue_media(sender: Event, order: Order, **kwargs):
    from pretix.base.models import ReusableMedium

    for p in order.positions.all():
        if p.item.media_policy in (Item.MEDIA_POLICY_NEW, Item.MEDIA_POLICY_REUSE_OR_NEW):
            mt = MEDIA_TYPES[p.item.media_type]
            if mt.medium_created_by_server and not p.linked_media.exists():
                rm = ReusableMedium.objects.create(
                    organizer=sender.organizer,
                    type=p.item.media_type,
                    identifier=mt.generate_identifier(sender.organizer),
                    active=True,
                    customer=order.customer,
                    linked_orderposition=p,
                )
                rm.log_action(
                    'pretix.reusable_medium.created',
                    data={
                        'by_order': order.code,
                        'linked_orderposition': p.pk,
                        'active': True,
                        'customer': order.customer_id,
                    }
                )
