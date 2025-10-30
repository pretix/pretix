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
from collections import defaultdict

import pycountry
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db.models import Q
from django.utils import formats
from django.utils.functional import cached_property
from django.utils.translation import (
    gettext as _, gettext_lazy, pgettext, pgettext_lazy,
)
from django_countries import countries
from django_countries.fields import Country
from i18nfield.strings import LazyI18nString
from phonenumber_field.phonenumber import to_python
from phonenumbers import SUPPORTED_REGIONS

from pretix.base.forms.questions import guess_country
from pretix.base.modelimport import (
    BooleanColumnMixin, DatetimeColumnMixin, DecimalColumnMixin, ImportColumn,
    SubeventColumnMixin, i18n_flat,
)
from pretix.base.models import (
    Customer, ItemVariation, OrderPosition, Question, QuestionAnswer,
    QuestionOption, Seat,
)
from pretix.base.services.pricing import get_price
from pretix.base.settings import (
    COUNTRIES_WITH_STATE_IN_ADDRESS, PERSON_NAME_SCHEMES,
)
from pretix.base.signals import order_import_columns


class EmailColumn(ImportColumn):
    identifier = 'email'
    verbose_name = gettext_lazy('Email address')
    order_level = True

    def clean(self, value, previous_values):
        if value:
            EmailValidator()(value)
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.email = value


class GroupingColumn(ImportColumn):
    identifier = 'grouping'
    verbose_name = gettext_lazy('Grouping')
    help_text = gettext_lazy(
        'Only applicable when "Import mode" is set to "Group multiple lines together...". Lines with the same grouping '
        'value will be put in the same order, but MUST be consecutive lines of the input file.'
    )
    order_level = True
    default_label = "---"

    def assign(self, value, order, position, invoice_address, **kwargs):
        pass


class PhoneColumn(ImportColumn):
    identifier = 'phone'
    verbose_name = gettext_lazy('Phone number')
    order_level = True

    def clean(self, value, previous_values):
        if value:
            if self.event.settings.region in SUPPORTED_REGIONS:
                region = self.event.settings.region
            elif self.event.settings.locale[:2].upper() in SUPPORTED_REGIONS:
                region = self.event.settings.locale[:2].upper()
            else:
                region = None

            phone_number = to_python(value, region)
            if not phone_number or not phone_number.is_valid():
                raise ValidationError(_('Enter a valid phone number.'))
            return phone_number
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.phone = value


class SubeventColumn(SubeventColumnMixin, ImportColumn):
    identifier = 'subevent'
    verbose_name = pgettext_lazy('subevents', 'Date')
    default_value = None
    help_text = pgettext_lazy(
        'subevents', 'The date can be specified through its full name, full date and time, or internal ID, provided '
                     'only one date in the system matches the input.'
    )

    def clean(self, value, previous_values):
        if not value:
            raise ValidationError(pgettext("subevent", "You need to select a date."))
        return super().clean(value, previous_values)

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.subevent = value


class ItemColumn(ImportColumn):
    identifier = 'item'
    verbose_name = gettext_lazy('Product')
    default_value = None
    help_text = gettext_lazy('The product can be specified by its internal ID, full name or internal name.')

    @cached_property
    def items(self):
        return list(self.event.items.filter(active=True))

    def static_choices(self):
        return [
            (str(p.pk), str(p)) for p in self.items
        ]

    def clean(self, value, previous_values):
        matches = [
            p for p in self.items
            if str(p.pk) == value or (p.internal_name and p.internal_name == value) or any(
                (v and v == value) for v in i18n_flat(p.name))
        ]
        if len(matches) == 0:
            raise ValidationError(_("No matching product was found."))
        if len(matches) > 1:
            raise ValidationError(_("Multiple matching products were found."))
        return matches[0]

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.item = value


class Variation(ImportColumn):
    identifier = 'variation'
    verbose_name = gettext_lazy('Product variation')
    help_text = gettext_lazy('The variation can be specified by its internal ID or full name.')

    @cached_property
    def items(self):
        return list(ItemVariation.objects.filter(
            active=True, item__active=True, item__event=self.event
        ).select_related('item'))

    def static_choices(self):
        return [
            (str(p.pk), '{} – {}'.format(p.item, p.value)) for p in self.items
        ]

    def clean(self, value, previous_values):
        if value:
            matches = [
                p for p in self.items
                if (str(p.pk) == value or any((v and v == value) for v in i18n_flat(p.value))) and p.item_id == previous_values['item'].pk
            ]
            if len(matches) == 0:
                raise ValidationError(_("No matching variation was found."))
            if len(matches) > 1:
                raise ValidationError(_("Multiple matching variations were found."))
            return matches[0]
        elif previous_values['item'].variations.exists():
            raise ValidationError(_("You need to select a variation for this product."))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.variation = value


class InvoiceAddressCompany(ImportColumn):
    identifier = 'invoice_address_company'
    order_level = True

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('Company')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.company = value or ''
        invoice_address.is_business = bool(value)


class InvoiceAddressNamePart(ImportColumn):
    order_level = True

    def __init__(self, event, key, label):
        self.key = key
        self.label = label
        super().__init__(event)

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + str(self.label)

    @property
    def identifier(self):
        return 'invoice_address_name_{}'.format(self.key)

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.name_parts[self.key] = value or ''


class InvoiceAddressStreet(ImportColumn):
    identifier = 'invoice_address_street'
    order_level = True

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('Address')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.street = value or ''


class InvoiceAddressZip(ImportColumn):
    identifier = 'invoice_address_zipcode'
    order_level = True

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('ZIP code')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.zipcode = value or ''


class InvoiceAddressCity(ImportColumn):
    identifier = 'invoice_address_city'
    order_level = True

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('City')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.city = value or ''


class InvoiceAddressCountry(ImportColumn):
    identifier = 'invoice_address_country'
    default_value = None
    help_text = gettext_lazy('The country needs to be specified using a two-letter country code.')
    order_level = True

    @property
    def initial(self):
        return 'static:' + str(guess_country(self.event))

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('Country')

    def static_choices(self):
        return list(countries)

    def clean(self, value, previous_values):
        if value and not (Country(value).numeric or value in settings.COUNTRIES_OVERRIDE):
            raise ValidationError(_("Please enter a valid country code."))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.country = value or ''


class InvoiceAddressState(ImportColumn):
    identifier = 'invoice_address_state'
    help_text = gettext_lazy('The state can be specified by its short form or full name.')
    order_level = True

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + pgettext('address', 'State')

    def clean(self, value, previous_values):
        if value:
            if previous_values.get('invoice_address_country') not in COUNTRIES_WITH_STATE_IN_ADDRESS:
                raise ValidationError(_("States are not supported for this country."))

            types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[previous_values.get('invoice_address_country')]
            match = [
                s for s in pycountry.subdivisions.get(country_code=previous_values.get('invoice_address_country'))
                if s.type in types and (s.code[3:] == value or s.name == value)
            ]
            if len(match) == 0:
                raise ValidationError(_("Please enter a valid state."))
            return match[0].code[3:]

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.state = value or ''


class InvoiceAddressVATID(ImportColumn):
    identifier = 'invoice_address_vat_id'
    order_level = True

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('VAT ID')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.vat_id = value or ''


class InvoiceAddressReference(ImportColumn):
    identifier = 'invoice_address_internal_reference'
    order_level = True

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('Internal reference')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.internal_reference = value or ''


class AttendeeNamePart(ImportColumn):
    def __init__(self, event, key, label):
        self.key = key
        self.label = label
        super().__init__(event)

    @property
    def verbose_name(self):
        return _('Attendee name') + ': ' + str(self.label)

    @property
    def identifier(self):
        return 'attendee_name_{}'.format(self.key)

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.attendee_name_parts[self.key] = value or ''


class AttendeeEmail(ImportColumn):
    identifier = 'attendee_email'
    verbose_name = gettext_lazy('Attendee email address')

    def clean(self, value, previous_values):
        if value:
            EmailValidator()(value)
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.attendee_email = value


class AttendeeCompany(ImportColumn):
    identifier = 'attendee_company'

    @property
    def verbose_name(self):
        return _('Attendee address') + ': ' + _('Company')

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.company = value or ''


class AttendeeStreet(ImportColumn):
    identifier = 'attendee_street'

    @property
    def verbose_name(self):
        return _('Attendee address') + ': ' + _('Address')

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.street = value or ''


class AttendeeZip(ImportColumn):
    identifier = 'attendee_zipcode'

    @property
    def verbose_name(self):
        return _('Attendee address') + ': ' + _('ZIP code')

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.zipcode = value or ''


class AttendeeCity(ImportColumn):
    identifier = 'attendee_city'

    @property
    def verbose_name(self):
        return _('Attendee address') + ': ' + _('City')

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.city = value or ''


class AttendeeCountry(ImportColumn):
    identifier = 'attendee_country'
    default_value = None
    help_text = gettext_lazy('The country needs to be specified using a two-letter country code.')

    @property
    def initial(self):
        return 'static:' + str(guess_country(self.event))

    @property
    def verbose_name(self):
        return _('Attendee address') + ': ' + _('Country')

    def static_choices(self):
        return list(countries)

    def clean(self, value, previous_values):
        if value and not (Country(value).numeric or value in settings.COUNTRIES_OVERRIDE):
            raise ValidationError(_("Please enter a valid country code."))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.country = value or ''


class AttendeeState(ImportColumn):
    identifier = 'attendee_state'
    help_text = gettext_lazy('The state can be specified by its short form or full name.')

    @property
    def verbose_name(self):
        return _('Attendee address') + ': ' + _('State')

    def clean(self, value, previous_values):
        if value:
            if previous_values.get('attendee_country') not in COUNTRIES_WITH_STATE_IN_ADDRESS:
                raise ValidationError(_("States are not supported for this country."))

            types, form = COUNTRIES_WITH_STATE_IN_ADDRESS[previous_values.get('attendee_country')]
            match = [
                s for s in pycountry.subdivisions.get(country_code=previous_values.get('attendee_country'))
                if s.type in types and (s.code[3:] == value or s.name == value)
            ]
            if len(match) == 0:
                raise ValidationError(_("Please enter a valid state."))
            return match[0].code[3:]

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.state = value or ''


class Price(DecimalColumnMixin, ImportColumn):
    identifier = 'price'
    verbose_name = gettext_lazy('Price')
    default_label = gettext_lazy('Calculate from product')

    def assign(self, value, order, position, invoice_address, **kwargs):
        if value is None:
            p = get_price(position.item, position.variation, position.voucher, subevent=position.subevent,
                          invoice_address=invoice_address)
        else:
            p = get_price(position.item, position.variation, position.voucher, subevent=position.subevent,
                          invoice_address=invoice_address, custom_price=value, force_custom_price=True)
        position.price = p.gross
        position.tax_rule = position.item.tax_rule
        position.tax_rate = p.rate
        position.tax_code = p.code
        position.tax_value = p.tax


class Secret(ImportColumn):
    identifier = 'secret'
    verbose_name = gettext_lazy('Ticket code')
    default_label = gettext_lazy('Generate automatically')

    def __init__(self, *args):
        self._cached = set()
        super().__init__(*args)

    def clean(self, value, previous_values):
        if value and (value in self._cached or OrderPosition.all.filter(order__event__organizer=self.event.organizer, secret=value).exists()):
            raise ValidationError(
                _('You cannot assign a position secret that already exists.')
            )
        self._cached.add(value)
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        if value:
            position.secret = value


class Locale(ImportColumn):
    identifier = 'locale'
    verbose_name = gettext_lazy('Order locale')
    default_value = None
    order_level = True

    @property
    def initial(self):
        return 'static:' + self.event.settings.locale

    def static_choices(self):
        locale_names = dict(settings.LANGUAGES)
        return [
            (a, locale_names[a]) for a in self.event.settings.locales
        ]

    def clean(self, value, previous_values):
        if not value:
            value = self.event.settings.locale
        if isinstance(value, str):
            value = value.lower()
        if value not in self.event.settings.locales:
            raise ValidationError(_("Please enter a valid language code."))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.locale = value


class ValidFrom(DatetimeColumnMixin, ImportColumn):
    identifier = 'valid_from'
    verbose_name = gettext_lazy('Valid from')

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.valid_from = value


class ValidUntil(DatetimeColumnMixin, ImportColumn):
    identifier = 'valid_until'
    verbose_name = gettext_lazy('Valid until')

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.valid_until = value


class Expires(DatetimeColumnMixin, ImportColumn):
    identifier = 'expires'
    verbose_name = gettext_lazy('Expiry date')
    order_level = True

    def clean(self, value, previous_values):
        if not value:
            return

        input_formats = formats.get_format('DATE_INPUT_FORMATS', use_l10n=True)
        for format in input_formats:
            try:
                d = datetime.datetime.strptime(value, format)
                d = d.replace(tzinfo=self.timezone, hour=23, minute=59, second=59)
                return d
            except (ValueError, TypeError):
                pass
        else:
            return super().clean(value, previous_values)  # parse date

    def assign(self, value, order, position, invoice_address, **kwargs):
        if value:
            order.expires = value


class Saleschannel(ImportColumn):
    identifier = 'sales_channel'
    verbose_name = gettext_lazy('Sales channel')
    default_value = None
    initial = 'static:web'
    help_text = gettext_lazy('The sales channel can be specified by it\'s internal identifier or its full name.')
    order_level = True

    @cached_property
    def channels(self):
        return list(self.event.organizer.sales_channels.all())

    def static_choices(self):
        return [
            (c.identifier, str(c.label)) for c in self.channels
        ]

    def clean(self, value, previous_values):
        matches = [
            p for p in self.channels
            if p.identifier == value or any((v and v == value) for v in i18n_flat(p.label))
        ]
        if len(matches) == 0:
            raise ValidationError(_("Please enter a valid sales channel."))
        if len(matches) > 1:
            raise ValidationError(_("Please enter a valid sales channel."))
        return matches[0]

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.sales_channel = value


class SeatColumn(ImportColumn):
    identifier = 'seat'
    verbose_name = gettext_lazy('Seat ID')
    help_text = gettext_lazy('The seat needs to be specified by its internal ID.')

    def __init__(self, *args):
        self._cached = set()
        super().__init__(*args)

    def clean(self, value, previous_values):
        if value:
            try:
                value = Seat.objects.get(
                    event=self.event,
                    seat_guid=value,
                    subevent=previous_values.get('subevent')
                )
            except Seat.MultipleObjectsReturned:
                raise ValidationError(_('Multiple matching seats were found.'))
            except Seat.DoesNotExist:
                raise ValidationError(_('No matching seat was found.'))
            if not value.is_available(sales_channel=previous_values.get('sales_channel')) or value in self._cached:
                raise ValidationError(
                    _('The seat you selected has already been taken. Please select a different seat.'))
            self._cached.add(value)
        elif previous_values['item'].seat_category_mappings.filter(subevent=previous_values.get('subevent')).exists():
            raise ValidationError(_('You need to select a specific seat.'))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.seat = value


class Comment(ImportColumn):
    identifier = 'comment'
    verbose_name = gettext_lazy('Order comment')
    order_level = True

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.comment = value or ''


class CheckinAttentionColumn(BooleanColumnMixin, ImportColumn):
    identifier = 'checkin_attention'
    verbose_name = gettext_lazy('Requires special attention')
    order_level = True

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.checkin_attention = value


class CheckinTextColumn(ImportColumn):
    identifier = 'checkin_text'
    verbose_name = gettext_lazy('Check-in text')
    order_level = True

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.checkin_text = value


class QuestionColumn(ImportColumn):
    def __init__(self, event, q):
        self.q = q
        self.option_resolve_cache = defaultdict(set)

        for opt in q.options.all():
            self.option_resolve_cache[str(opt.id)].add(opt)
            self.option_resolve_cache[opt.identifier].add(opt)

            if isinstance(opt.answer, LazyI18nString):

                if isinstance(opt.answer.data, dict):
                    for v in opt.answer.data.values():
                        self.option_resolve_cache[v.strip()].add(opt)
                else:
                    self.option_resolve_cache[opt.answer.data.strip()].add(opt)

            else:
                self.option_resolve_cache[opt.answer.strip()].add(opt)
        super().__init__(event)

    @property
    def verbose_name(self):
        return _('Question') + ': ' + str(self.q.question)

    @property
    def identifier(self):
        return 'question_{}'.format(self.q.pk)

    def clean(self, value, previous_values):
        if value:
            if self.q.type == Question.TYPE_CHOICE:
                if value not in self.option_resolve_cache:
                    raise ValidationError(_('Invalid option selected.'))
                if len(self.option_resolve_cache[value]) > 1:
                    raise ValidationError(_('Ambiguous option selected.'))
                return list(self.option_resolve_cache[value])[0]

            elif self.q.type == Question.TYPE_CHOICE_MULTIPLE:
                values = value.split(',')
                if any(v.strip() not in self.option_resolve_cache for v in values):
                    raise ValidationError(_('Invalid option selected.'))
                if any(len(self.option_resolve_cache[v.strip()]) > 1 for v in values):
                    raise ValidationError(_('Ambiguous option selected.'))
                return [list(self.option_resolve_cache[v.strip()])[0] for v in values]

            else:
                return self.q.clean_answer(value)

    def assign(self, value, order, position, invoice_address, **kwargs):
        if value is not None:
            if not hasattr(order, '_answers'):
                order._answers = []
            if isinstance(value, QuestionOption):
                a = QuestionAnswer(orderposition=position, question=self.q, answer=str(value))
                a._options = [value]
                order._answers.append(a)
            elif isinstance(value, list):
                a = QuestionAnswer(orderposition=position, question=self.q, answer=', '.join(str(v) for v in value))
                a._options = value
                order._answers.append(a)
            else:
                order._answers.append(QuestionAnswer(question=self.q, answer=str(value), orderposition=position))

    def save(self, order):
        for a in getattr(order, '_answers', []):
            a.orderposition = a.orderposition  # This is apparently required after save() again
            a.save()
            if hasattr(a, '_options'):
                a.options.add(*a._options)


class CustomerColumn(ImportColumn):
    identifier = 'customer'
    verbose_name = gettext_lazy('Customer')
    order_level = True

    def clean(self, value, previous_values):
        if value:
            try:
                value = self.event.organizer.customers.get(
                    Q(identifier=value) | Q(email__iexact=value) | Q(external_identifier=value)
                )
            except Customer.MultipleObjectsReturned:
                value = self.event.organizer.customers.get(
                    Q(identifier=value)
                )
            except Customer.DoesNotExist:
                raise ValidationError(_('No matching customer was found.'))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.customer = value


def get_order_import_columns(event):
    default = []
    if event.has_subevents:
        default.append(SubeventColumn(event))
    default += [
        GroupingColumn(event),
        EmailColumn(event),
        PhoneColumn(event),
        ItemColumn(event),
        Variation(event),
        InvoiceAddressCompany(event),
    ]
    if event.settings.customer_accounts:
        default += [
            CustomerColumn(event),
        ]
    scheme = PERSON_NAME_SCHEMES.get(event.settings.name_scheme)
    for n, l, w in scheme['fields']:
        default.append(InvoiceAddressNamePart(event, n, l))
    default += [
        InvoiceAddressStreet(event),
        InvoiceAddressZip(event),
        InvoiceAddressCity(event),
        InvoiceAddressCountry(event),
        InvoiceAddressState(event),
        InvoiceAddressVATID(event),
        InvoiceAddressReference(event),
    ]
    for n, l, w in scheme['fields']:
        default.append(AttendeeNamePart(event, n, l))
    default += [
        AttendeeEmail(event),
        AttendeeCompany(event),
        AttendeeStreet(event),
        AttendeeZip(event),
        AttendeeCity(event),
        AttendeeCountry(event),
        AttendeeState(event),
        Price(event),
        Secret(event),
        Saleschannel(event),
        SeatColumn(event),
        ValidFrom(event),
        ValidUntil(event),
        Locale(event),
        CheckinAttentionColumn(event),
        CheckinTextColumn(event),
        Expires(event),
        Comment(event),
    ]
    for q in event.questions.prefetch_related('options').exclude(type=Question.TYPE_FILE):
        default.append(QuestionColumn(event, q))

    for recv, resp in order_import_columns.send(sender=event):
        default += resp

    return default
