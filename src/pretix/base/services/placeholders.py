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
import inspect
import logging
from datetime import timedelta
from decimal import Decimal

from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from pretix.base.forms import PlaceholderValidator
from pretix.base.forms.widgets import format_placeholders_help_text
from pretix.base.i18n import (
    LazyCurrencyNumber, LazyDate, LazyExpiresDate, LazyNumber,
)
from pretix.base.reldate import RelativeDateWrapper
from pretix.base.settings import PERSON_NAME_SCHEMES, get_name_parts_localized
from pretix.base.signals import (
    register_mail_placeholders, register_text_placeholders,
)
from pretix.helpers.format import SafeFormatter

logger = logging.getLogger('pretix.base.services.placeholders')


class BaseTextPlaceholder:
    """
    This is the base class for all email text placeholders.
    """

    @property
    def required_context(self):
        """
        This property should return a list of all attribute names that need to be
        contained in the base context so that this placeholder is available. By default,
        it returns a list containing the string "event".
        """
        return ["event"]

    @property
    def identifier(self):
        """
        This should return the identifier of this placeholder in the email.
        """
        raise NotImplementedError()

    def render(self, context):
        """
        This method is called to generate the actual text that is being
        used in the email. You will be passed a context dictionary with the
        base context attributes specified in ``required_context``. You are
        expected to return a plain-text string.
        """
        raise NotImplementedError()

    def render_sample(self, event):
        """
        This method is called to generate a text to be used in email previews.
        This may only depend on the event.
        """
        raise NotImplementedError()


class SimpleFunctionalTextPlaceholder(BaseTextPlaceholder):
    def __init__(self, identifier, args, func, sample):
        self._identifier = identifier
        self._args = args
        self._func = func
        self._sample = sample

    @property
    def identifier(self):
        return self._identifier

    @property
    def required_context(self):
        return self._args

    def render(self, context):
        return self._func(**{k: context[k] for k in self._args})

    def render_sample(self, event):
        if callable(self._sample):
            return self._sample(event)
        else:
            return self._sample


class PlaceholderContext(SafeFormatter):
    """
    Holds the contextual arguments and corresponding list of available placeholders for formatting
    an email or other templated text.

    Example:
        context = PlaceholderContext(event=my_event, order=my_order)
        formatted_doc = context.format(input_doc)
    """
    def __init__(self, **kwargs):
        super().__init__({})
        self.context_args = kwargs
        self._extend_context_args()
        self.placeholders = {}
        self.cache = {}
        event = kwargs['event']
        for r, val in [
            *register_mail_placeholders.send(sender=event),
            *register_text_placeholders.send(sender=event)
        ]:
            if not isinstance(val, (list, tuple)):
                val = [val]
            for v in val:
                if all(rp in kwargs for rp in v.required_context):
                    self.placeholders[v.identifier] = v

    def _extend_context_args(self):
        from pretix.base.models import InvoiceAddress

        if 'position' in self.context_args:
            self.context_args.setdefault("position_or_address", self.context_args['position'])
        if 'order' in self.context_args:
            try:
                if not self.context_args.get('invoice_address'):
                    self.context_args['invoice_address'] = self.context_args['order'].invoice_address
            except InvoiceAddress.DoesNotExist:
                self.context_args['invoice_address'] = InvoiceAddress(order=self.context_args['order'])
            finally:
                self.context_args.setdefault("position_or_address", self.context_args['invoice_address'])

    def render_placeholder(self, placeholder):
        try:
            return self.cache[placeholder.identifier]
        except KeyError:
            try:
                value = self.cache[placeholder.identifier] = placeholder.render(self.context_args)
                return value
            except:
                logger.exception(f'Failed to process template placeholder {placeholder.identifier}.')
                return '(error)'

    def render_all(self):
        return {identifier: self.render_placeholder(placeholder)
                for (identifier, placeholder) in self.placeholders.items()}

    def get_value(self, key, args, kwargs):
        if key not in self.placeholders:
            return '{' + str(key) + '}'
        return self.render_placeholder(self.placeholders[key])


def _placeholder_payments(order, payments):
    d = []
    for payment in payments:
        if 'payment' in inspect.signature(payment.payment_provider.order_pending_mail_render).parameters:
            d.append(str(payment.payment_provider.order_pending_mail_render(order, payment)))
        else:
            d.append(str(payment.payment_provider.order_pending_mail_render(order)))
    d = [line for line in d if line.strip()]
    if d:
        return '\n\n'.join(d)
    else:
        return ''


def get_best_name(position_or_address, parts=False):
    """
    Return the best name we got for either an invoice address or an order position, falling back to the respective other
    """
    from pretix.base.models import InvoiceAddress, OrderPosition
    if isinstance(position_or_address, InvoiceAddress):
        if position_or_address.name:
            return position_or_address.name_parts if parts else position_or_address.name
        elif position_or_address.order:
            position_or_address = position_or_address.order.positions.exclude(attendee_name_cached="").exclude(attendee_name_cached__isnull=True).first()

    if isinstance(position_or_address, OrderPosition):
        if position_or_address.attendee_name:
            return position_or_address.attendee_name_parts if parts else position_or_address.attendee_name
        elif position_or_address.order:
            try:
                return position_or_address.order.invoice_address.name_parts if parts else position_or_address.order.invoice_address.name
            except InvoiceAddress.DoesNotExist:
                pass

    return {} if parts else ""


@receiver(register_text_placeholders, dispatch_uid="pretixbase_register_text_placeholders")
def base_placeholders(sender, **kwargs):
    from pretix.multidomain.urlreverse import build_absolute_uri

    ph = [
        SimpleFunctionalTextPlaceholder(
            'event', ['event'], lambda event: event.name, lambda event: event.name
        ),
        SimpleFunctionalTextPlaceholder(
            'event', ['event_or_subevent'], lambda event_or_subevent: event_or_subevent.name,
            lambda event_or_subevent: event_or_subevent.name
        ),
        SimpleFunctionalTextPlaceholder(
            'event_slug', ['event'], lambda event: event.slug, lambda event: event.slug
        ),
        SimpleFunctionalTextPlaceholder(
            'code', ['order'], lambda order: order.code, 'F8VVL'
        ),
        SimpleFunctionalTextPlaceholder(
            'total', ['order'], lambda order: LazyNumber(order.total), lambda event: LazyNumber(Decimal('42.23'))
        ),
        SimpleFunctionalTextPlaceholder(
            'currency', ['event'], lambda event: event.currency, lambda event: event.currency
        ),
        SimpleFunctionalTextPlaceholder(
            'order_email', ['order'], lambda order: order.email, 'john@example.org'
        ),
        SimpleFunctionalTextPlaceholder(
            'invoice_number', ['invoice'],
            lambda invoice: invoice.full_invoice_no,
            f'{sender.settings.invoice_numbers_prefix or (sender.slug.upper() + "-")}00000'
        ),
        SimpleFunctionalTextPlaceholder(
            'refund_amount', ['event_or_subevent', 'refund_amount'],
            lambda event_or_subevent, refund_amount: LazyCurrencyNumber(refund_amount, event_or_subevent.currency),
            lambda event_or_subevent: LazyCurrencyNumber(Decimal('42.23'), event_or_subevent.currency)
        ),
        SimpleFunctionalTextPlaceholder(
            'pending_sum', ['event', 'pending_sum'],
            lambda event, pending_sum: LazyCurrencyNumber(pending_sum, event.currency),
            lambda event: LazyCurrencyNumber(Decimal('42.23'), event.currency)
        ),
        SimpleFunctionalTextPlaceholder(
            'total_with_currency', ['event', 'order'], lambda event, order: LazyCurrencyNumber(order.total,
                                                                                               event.currency),
            lambda event: LazyCurrencyNumber(Decimal('42.23'), event.currency)
        ),
        SimpleFunctionalTextPlaceholder(
            'expire_date', ['event', 'order'], lambda event, order: LazyExpiresDate(order.expires.astimezone(event.timezone)),
            lambda event: LazyDate(now() + timedelta(days=15))
        ),
        SimpleFunctionalTextPlaceholder(
            'url', ['order', 'event'], lambda order, event: build_absolute_uri(
                event,
                'presale:event.order.open', kwargs={
                    'order': order.code,
                    'secret': order.secret,
                    'hash': order.email_confirm_hash()
                }
            ), lambda event: build_absolute_uri(
                event,
                'presale:event.order.open', kwargs={
                    'order': 'F8VVL',
                    'secret': '6zzjnumtsx136ddy',
                    'hash': '98kusd8ofsj8dnkd'
                }
            ),
        ),
        SimpleFunctionalTextPlaceholder(
            'url_info_change', ['order', 'event'], lambda order, event: build_absolute_uri(
                event,
                'presale:event.order.modify', kwargs={
                    'order': order.code,
                    'secret': order.secret,
                }
            ), lambda event: build_absolute_uri(
                event,
                'presale:event.order.modify', kwargs={
                    'order': 'F8VVL',
                    'secret': '6zzjnumtsx136ddy',
                }
            ),
        ),
        SimpleFunctionalTextPlaceholder(
            'url_products_change', ['order', 'event'], lambda order, event: build_absolute_uri(
                event,
                'presale:event.order.change', kwargs={
                    'order': order.code,
                    'secret': order.secret,
                }
            ), lambda event: build_absolute_uri(
                event,
                'presale:event.order.change', kwargs={
                    'order': 'F8VVL',
                    'secret': '6zzjnumtsx136ddy',
                }
            ),
        ),
        SimpleFunctionalTextPlaceholder(
            'url_cancel', ['order', 'event'], lambda order, event: build_absolute_uri(
                event,
                'presale:event.order.cancel', kwargs={
                    'order': order.code,
                    'secret': order.secret,
                }
            ), lambda event: build_absolute_uri(
                event,
                'presale:event.order.cancel', kwargs={
                    'order': 'F8VVL',
                    'secret': '6zzjnumtsx136ddy',
                }
            ),
        ),
        SimpleFunctionalTextPlaceholder(
            'url', ['event', 'position'], lambda event, position: build_absolute_uri(
                event,
                'presale:event.order.position',
                kwargs={
                    'order': position.order.code,
                    'secret': position.web_secret,
                    'position': position.positionid
                }
            ),
            lambda event: build_absolute_uri(
                event,
                'presale:event.order.position', kwargs={
                    'order': 'F8VVL',
                    'secret': '6zzjnumtsx136ddy',
                    'position': '123'
                }
            ),
        ),
        SimpleFunctionalTextPlaceholder(
            'order_modification_deadline_date_and_time', ['order', 'event'],
            lambda order, event:
            date_format(order.modify_deadline.astimezone(event.timezone), 'SHORT_DATETIME_FORMAT')
            if order.modify_deadline
            else '',
            lambda event: date_format(
                event.settings.get(
                    'last_order_modification_date', as_type=RelativeDateWrapper
                ).datetime(event).astimezone(event.timezone),
                'SHORT_DATETIME_FORMAT'
            ) if event.settings.get('last_order_modification_date') else '',
        ),
        SimpleFunctionalTextPlaceholder(
            'event_location', ['event_or_subevent'], lambda event_or_subevent: str(event_or_subevent.location or ''),
            lambda event: str(event.location or ''),
        ),
        SimpleFunctionalTextPlaceholder(
            'event_admission_time', ['event_or_subevent'],
            lambda event_or_subevent:
                date_format(event_or_subevent.date_admission.astimezone(event_or_subevent.timezone), 'TIME_FORMAT')
                if event_or_subevent.date_admission
                else '',
            lambda event: date_format(event.date_admission.astimezone(event.timezone), 'TIME_FORMAT') if event.date_admission else '',
        ),
        SimpleFunctionalTextPlaceholder(
            'subevent', ['waiting_list_entry', 'event'],
            lambda waiting_list_entry, event: str(waiting_list_entry.subevent or event),
            lambda event: str(event if not event.has_subevents or not event.subevents.exists() else event.subevents.first())
        ),
        SimpleFunctionalTextPlaceholder(
            'subevent_date_from', ['waiting_list_entry', 'event'],
            lambda waiting_list_entry, event: (waiting_list_entry.subevent or event).get_date_from_display(),
            lambda event: (event if not event.has_subevents or not event.subevents.exists() else event.subevents.first()).get_date_from_display()
        ),
        SimpleFunctionalTextPlaceholder(
            'url_remove', ['waiting_list_voucher', 'event'],
            lambda waiting_list_voucher, event: build_absolute_uri(
                event, 'presale:event.waitinglist.remove'
            ) + '?voucher=' + waiting_list_voucher.code,
            lambda event: build_absolute_uri(
                event,
                'presale:event.waitinglist.remove',
            ) + '?voucher=68CYU2H6ZTP3WLK5',
        ),
        SimpleFunctionalTextPlaceholder(
            'url', ['waiting_list_voucher', 'event'],
            lambda waiting_list_voucher, event: build_absolute_uri(
                event, 'presale:event.redeem'
            ) + '?voucher=' + waiting_list_voucher.code,
            lambda event: build_absolute_uri(
                event,
                'presale:event.redeem',
            ) + '?voucher=68CYU2H6ZTP3WLK5',
        ),
        SimpleFunctionalTextPlaceholder(
            'invoice_name', ['invoice_address'], lambda invoice_address: invoice_address.name or '',
            _('John Doe')
        ),
        SimpleFunctionalTextPlaceholder(
            'invoice_company', ['invoice_address'], lambda invoice_address: invoice_address.company or '',
            _('Sample Corporation')
        ),
        SimpleFunctionalTextPlaceholder(
            'orders', ['event', 'orders'], lambda event, orders: '\n' + '\n\n'.join(
                '* {} - {}'.format(
                    order.full_code,
                    build_absolute_uri(event, 'presale:event.order.open', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'order': order.code,
                        'secret': order.secret,
                        'hash': order.email_confirm_hash(),
                    }),
                )
                for order in orders
            ), lambda event: '\n' + '\n\n'.join(
                '* {} - {}'.format(
                    '{}-{}'.format(event.slug.upper(), order['code']),
                    build_absolute_uri(event, 'presale:event.order.open', kwargs={
                        'event': event.slug,
                        'organizer': event.organizer.slug,
                        'order': order['code'],
                        'secret': order['secret'],
                        'hash': order['hash'],
                    }),
                )
                for order in [
                    {'code': 'F8VVL', 'secret': '6zzjnumtsx136ddy', 'hash': 'abcdefghi'},
                    {'code': 'HIDHK', 'secret': '98kusd8ofsj8dnkd', 'hash': 'jklmnopqr'},
                    {'code': 'OPKSB', 'secret': '09pjdksflosk3njd', 'hash': 'stuvwxy2z'}
                ]
            ),
        ),
        SimpleFunctionalTextPlaceholder(
            'hours', ['event', 'waiting_list_entry'], lambda event, waiting_list_entry:
            event.settings.waiting_list_hours,
            lambda event: event.settings.waiting_list_hours
        ),
        SimpleFunctionalTextPlaceholder(
            'product', ['waiting_list_entry'], lambda waiting_list_entry: waiting_list_entry.item.name,
            _('Sample Admission Ticket')
        ),
        SimpleFunctionalTextPlaceholder(
            'code', ['waiting_list_voucher'], lambda waiting_list_voucher: waiting_list_voucher.code,
            '68CYU2H6ZTP3WLK5'
        ),
        SimpleFunctionalTextPlaceholder(
            # join vouchers with two spaces at end of line so markdown-parser inserts a <br>
            'voucher_list', ['voucher_list'], lambda voucher_list: '  \n'.join(voucher_list),
            '    68CYU2H6ZTP3WLK5\n    7MB94KKPVEPSMVF2'
        ),
        SimpleFunctionalTextPlaceholder(
            # join vouchers with two spaces at end of line so markdown-parser inserts a <br>
            'voucher_url_list', ['event', 'voucher_list'],
            lambda event, voucher_list: '  \n'.join([
                build_absolute_uri(
                    event, 'presale:event.redeem'
                ) + '?voucher=' + c
                for c in voucher_list
            ]),
            lambda event: '  \n'.join([
                build_absolute_uri(
                    event, 'presale:event.redeem'
                ) + '?voucher=' + c
                for c in ['68CYU2H6ZTP3WLK5', '7MB94KKPVEPSMVF2']
            ]),
        ),
        SimpleFunctionalTextPlaceholder(
            'url', ['event', 'voucher_list'], lambda event, voucher_list: build_absolute_uri(event, 'presale:event.index', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            }), lambda event: build_absolute_uri(event, 'presale:event.index', kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            })
        ),
        SimpleFunctionalTextPlaceholder(
            'name', ['name'], lambda name: name,
            _('John Doe')
        ),
        SimpleFunctionalTextPlaceholder(
            'comment', ['comment'], lambda comment: comment,
            _('An individual text with a reason can be inserted here.'),
        ),
        SimpleFunctionalTextPlaceholder(
            'payment_info', ['order', 'payments'], _placeholder_payments,
            _('The amount has been charged to your card.'),
        ),
        SimpleFunctionalTextPlaceholder(
            'payment_info', ['payment_info'], lambda payment_info: payment_info,
            _('Please transfer money to this bank account: 9999-9999-9999-9999'),
        ),
        SimpleFunctionalTextPlaceholder(
            'attendee_name', ['position'], lambda position: position.attendee_name,
            _('John Doe'),
        ),
        SimpleFunctionalTextPlaceholder(
            'positionid', ['position'], lambda position: str(position.positionid),
            '1'
        ),
        SimpleFunctionalTextPlaceholder(
            'name', ['position_or_address'],
            get_best_name,
            _('John Doe'),
        ),
    ]

    name_scheme = PERSON_NAME_SCHEMES[sender.settings.name_scheme]
    if "concatenation_for_salutation" in name_scheme:
        concatenation_for_salutation = name_scheme["concatenation_for_salutation"]
    else:
        concatenation_for_salutation = name_scheme["concatenation"]

    ph.append(SimpleFunctionalTextPlaceholder(
        "name_for_salutation", ["waiting_list_entry"],
        lambda waiting_list_entry: concatenation_for_salutation(waiting_list_entry.name_parts),
        lambda event: concatenation_for_salutation(name_scheme['sample']),
    ))
    ph.append(SimpleFunctionalTextPlaceholder(
        "name", ["waiting_list_entry"],
        lambda waiting_list_entry: waiting_list_entry.name or "",
        _("Mr Doe"),
    ))
    ph.append(SimpleFunctionalTextPlaceholder(
        "name_for_salutation", ["position_or_address"],
        lambda position_or_address: concatenation_for_salutation(get_best_name(position_or_address, parts=True)),
        lambda event: concatenation_for_salutation(name_scheme['sample']),
    ))

    for f, l, w in name_scheme['fields']:
        if f == 'full_name':
            continue
        ph.append(SimpleFunctionalTextPlaceholder(
            'name_%s' % f, ['waiting_list_entry'], lambda waiting_list_entry, f=f: get_name_parts_localized(waiting_list_entry.name_parts, f),
            name_scheme['sample'][f]
        ))
        ph.append(SimpleFunctionalTextPlaceholder(
            'attendee_name_%s' % f, ['position'], lambda position, f=f: get_name_parts_localized(position.attendee_name_parts, f),
            name_scheme['sample'][f]
        ))
        ph.append(SimpleFunctionalTextPlaceholder(
            'name_%s' % f, ['position_or_address'],
            lambda position_or_address, f=f: get_name_parts_localized(get_best_name(position_or_address, parts=True), f),
            name_scheme['sample'][f]
        ))

    for k, v in sender.meta_data.items():
        ph.append(SimpleFunctionalTextPlaceholder(
            'meta_%s' % k, ['event'], lambda event, k=k: event.meta_data[k],
            v
        ))
        ph.append(SimpleFunctionalTextPlaceholder(
            'meta_%s' % k, ['event_or_subevent'], lambda event_or_subevent, k=k: event_or_subevent.meta_data[k],
            v
        ))

    return ph


class FormPlaceholderMixin:
    def _set_field_placeholders(self, fn, base_parameters):
        placeholders = get_available_placeholders(self.event, base_parameters)
        ht = format_placeholders_help_text(placeholders, self.event)
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(['{%s}' % p for p in placeholders.keys()])
        )


def get_available_placeholders(event, base_parameters):
    if 'order' in base_parameters:
        base_parameters.append('invoice_address')
        base_parameters.append('position_or_address')
    params = {}
    for r, val in [*register_mail_placeholders.send(sender=event), *register_text_placeholders.send(sender=event)]:
        if not isinstance(val, (list, tuple)):
            val = [val]
        for v in val:
            if all(rp in base_parameters for rp in v.required_context):
                params[v.identifier] = v
    return params
