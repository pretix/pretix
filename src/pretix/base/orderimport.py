import re
from decimal import Decimal, DecimalException

import pycountry
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.utils import formats
from django.utils.functional import cached_property
from django.utils.translation import (
    gettext as _, gettext_lazy, pgettext, pgettext_lazy,
)
from django_countries import countries
from django_countries.fields import Country

from pretix.base.channels import get_all_sales_channels
from pretix.base.forms.questions import guess_country
from pretix.base.models import (
    ItemVariation, OrderPosition, QuestionAnswer, QuestionOption, Seat,
)
from pretix.base.services.pricing import get_price
from pretix.base.settings import (
    COUNTRIES_WITH_STATE_IN_ADDRESS, PERSON_NAME_SCHEMES,
)
from pretix.base.signals import order_import_columns


class ImportColumn:
    @property
    def identifier(self):
        """
        Unique, internal name of the column.
        """
        raise NotImplementedError

    @property
    def verbose_name(self):
        """
        Human-readable description of the column
        """
        raise NotImplementedError

    @property
    def initial(self):
        """
        Initial value for the form component
        """
        return None

    @property
    def default_value(self):
        """
        Internal default value for the assignment of this column. Defaults to ``empty``. Return ``None`` to disable this
        option.
        """
        return 'empty'

    @property
    def default_label(self):
        """
        Human-readable description of the default assignment of this column, defaults to "Keep empty".
        """
        return gettext_lazy('Keep empty')

    def __init__(self, event):
        self.event = event

    def static_choices(self):
        """
        This will be called when rendering the form component and allows you to return a list of values that can be
        selected by the user statically during import.

        :return: list of 2-tuples of strings
        """
        return []

    def resolve(self, settings, record):
        """
        This method will be called to get the raw value for this field, usually by either using a static value or
        inspecting the CSV file for the assigned header. You usually do not need to implement this on your own,
        the default should be fine.
        """
        k = settings.get(self.identifier, self.default_value)
        if k == self.default_value:
            return None
        elif k.startswith('csv:'):
            return record.get(k[4:], None) or None
        elif k.startswith('static:'):
            return k[7:]
        raise ValidationError(_('Invalid setting for column "{header}".').format(header=self.verbose_name))

    def clean(self, value, previous_values):
        """
        Allows you to validate the raw input value for your column. Raise ``ValidationError`` if the value is invalid.
        You do not need to include the column or row name or value in the error message as it will automatically be
        included.

        :param value: Contains the raw value of your column as returned by ``resolve``. This can usually be ``None``,
                      e.g. if the column is empty or does not exist in this row.
        :param previous_values: Dictionary containing the validated values of all columns that have already been validated.
        """
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        """
        This will be called to perform the actual import. You are supposed to set attributes on the ``order``, ``position``,
        or ``invoice_address`` objects based on the input ``value``. This is called *before* the actual database
        transaction, so these three objects do not yet have a primary key. If you want to create related objects, you
        need to place them into some sort of internal queue and persist them when ``save`` is called.
        """
        pass

    def save(self, order):
        """
        This will be called to perform the actual import. This is called inside the actual database transaction and the
        input object ``order`` has already been saved to the database.
        """
        pass


class EmailColumn(ImportColumn):
    identifier = 'email'
    verbose_name = gettext_lazy('E-mail address')

    def clean(self, value, previous_values):
        if value:
            EmailValidator()(value)
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.email = value


class SubeventColumn(ImportColumn):
    identifier = 'subevent'
    verbose_name = pgettext_lazy('subevents', 'Date')
    default_value = None

    @cached_property
    def subevents(self):
        return list(self.event.subevents.filter(active=True).order_by('date_from'))

    def static_choices(self):
        return [
            (str(p.pk), str(p)) for p in self.subevents
        ]

    def clean(self, value, previous_values):
        if not value:
            raise ValidationError(pgettext("subevent", "You need to select a date."))
        matches = [
            p for p in self.subevents
            if str(p.pk) == value or any(
                (v and v == value) for v in i18n_flat(p.name)) or p.date_from.isoformat() == value
        ]
        if len(matches) == 0:
            raise ValidationError(pgettext("subevent", "No matching date was found."))
        if len(matches) > 1:
            raise ValidationError(pgettext("subevent", "Multiple matching dates were found."))
        return matches[0]

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.subevent = value


def i18n_flat(l):
    if isinstance(l.data, dict):
        return l.data.values()
    return [l.data]


class ItemColumn(ImportColumn):
    identifier = 'item'
    verbose_name = gettext_lazy('Product')
    default_value = None

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
                if str(p.pk) == value or any((v and v == value) for v in i18n_flat(p.value)) and p.item_id == previous_values['item'].pk
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

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('Company')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.company = value or ''
        invoice_address.is_business = bool(value)


class InvoiceAddressNamePart(ImportColumn):
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

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('Address')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.address = value or ''


class InvoiceAddressZip(ImportColumn):
    identifier = 'invoice_address_zipcode'

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('ZIP code')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.zipcode = value or ''


class InvoiceAddressCity(ImportColumn):
    identifier = 'invoice_address_city'

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('City')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.city = value or ''


class InvoiceAddressCountry(ImportColumn):
    identifier = 'invoice_address_country'
    default_value = None

    @property
    def initial(self):
        return 'static:' + str(guess_country(self.event))

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('Country')

    def static_choices(self):
        return list(countries)

    def clean(self, value, previous_values):
        if value and not Country(value).numeric:
            raise ValidationError(_("Please enter a valid country code."))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.country = value


class InvoiceAddressState(ImportColumn):
    identifier = 'invoice_address_state'

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('State')

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

    @property
    def verbose_name(self):
        return _('Invoice address') + ': ' + _('VAT ID')

    def assign(self, value, order, position, invoice_address, **kwargs):
        invoice_address.vat_id = value or ''


class InvoiceAddressReference(ImportColumn):
    identifier = 'invoice_address_internal_reference'

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
    verbose_name = gettext_lazy('Attendee e-mail address')

    def clean(self, value, previous_values):
        if value:
            EmailValidator()(value)
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        position.attendee_email = value


class Price(ImportColumn):
    identifier = 'price'
    verbose_name = gettext_lazy('Price')
    default_label = gettext_lazy('Calculate from product')

    def clean(self, value, previous_values):
        if value not in (None, ''):
            value = formats.sanitize_separators(re.sub(r'[^0-9.,-]', '', value))
            try:
                value = Decimal(value)
            except (DecimalException, TypeError):
                raise ValidationError(_('You entered an invalid number.'))
            return value

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
        position.tax_value = p.tax


class Secret(ImportColumn):
    identifier = 'secret'
    verbose_name = gettext_lazy('Ticket code')
    default_label = gettext_lazy('Generate automatically')

    def __init__(self, *args):
        self._cached = set()
        super().__init__(*args)

    def clean(self, value, previous_values):
        if value and (value in self._cached or OrderPosition.all.filter(order__event=self.event, secret=value).exists()):
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
        if value not in self.event.settings.locales:
            raise ValidationError(_("Please enter a valid language code."))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.locale = value


class Saleschannel(ImportColumn):
    identifier = 'sales_channel'
    verbose_name = gettext_lazy('Sales channel')

    def static_choices(self):
        return [
            (sc.identifier, sc.verbose_name) for sc in get_all_sales_channels().values()
        ]

    def clean(self, value, previous_values):
        if not value:
            value = 'web'
        if value not in get_all_sales_channels():
            raise ValidationError(_("Please enter a valid sales channel."))
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.sales_channel = value


class SeatColumn(ImportColumn):
    identifier = 'seat'
    verbose_name = gettext_lazy('Seat ID')

    def __init__(self, *args):
        self._cached = set()
        super().__init__(*args)

    def clean(self, value, previous_values):
        if value:
            try:
                value = Seat.objects.get(
                    seat_guid=value,
                    subevent=previous_values.get('subevent')
                )
            except Seat.DoesNotExist:
                raise ValidationError(_('No matching seat was found.'))
            if not value.is_available() or value in self._cached:
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
    verbose_name = gettext_lazy('Comment')

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.comment = value or ''


class QuestionColumn(ImportColumn):
    def __init__(self, event, q):
        self.q = q
        super().__init__(event)

    @property
    def verbose_name(self):
        return _('Question') + ': ' + str(self.q.question)

    @property
    def identifier(self):
        return 'question_{}'.format(self.q.pk)

    def clean(self, value, previous_values):
        if value:
            return self.q.clean_answer(value)

    def assign(self, value, order, position, invoice_address, **kwargs):
        if value:
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


def get_all_columns(event):
    default = []
    if event.has_subevents:
        default.append(SubeventColumn(event))
    default += [
        EmailColumn(event),
        ItemColumn(event),
        Variation(event),
        InvoiceAddressCompany(event),
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
        Price(event),
        Secret(event),
        Locale(event),
        Saleschannel(event),
        SeatColumn(event),
        Comment(event)
    ]
    for q in event.questions.exclude(type='F'):
        default.append(QuestionColumn(event, q))

    for recv, resp in order_import_columns.send(sender=event):
        default += resp

    return default
