import csv
import io
import re
from decimal import Decimal, DecimalException

import pycountry
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.utils import formats
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext as _, gettext_lazy
from django_countries import countries
from django_countries.fields import Country

from pretix.base.channels import get_all_sales_channels
from pretix.base.forms.questions import guess_country
from pretix.base.i18n import LazyLocaleException, language
from pretix.base.models import (
    CachedFile, Event, InvoiceAddress, ItemVariation, Order, OrderPayment,
    OrderPosition, QuestionOption, User,
)
from pretix.base.services.invoices import generate_invoice, invoice_qualified
from pretix.base.services.pricing import get_price
from pretix.base.services.tasks import ProfiledEventTask
from pretix.base.settings import (
    COUNTRIES_WITH_STATE_IN_ADDRESS, PERSON_NAME_SCHEMES,
)
from pretix.base.signals import order_paid, order_placed
from pretix.celery_app import app


class DataImportError(LazyLocaleException):
    def __init__(self, *args):
        msg = args[0]
        msgargs = args[1] if len(args) > 1 else None
        self.args = args
        if msgargs:
            msg = _(msg) % msgargs
        else:
            msg = _(msg)
        super().__init__(msg)


class ImportColumn:
    identifier = None
    verbose_name = None
    default_value = 'empty'
    default_label = gettext_lazy('Keep empty')
    initial = None

    def __init__(self, event):
        self.event = event

    def static_choices(self):
        return []

    def resolve(self, settings, record):
        k = settings.get(self.identifier, self.default_value)
        if k == self.default_value:
            return None
        elif k.startswith('csv:'):
            return record.get(k[4:], None) or None
        elif k.startswith('static:'):
            return k[7:]
        raise ValidationError(_('Invalid setting for column "{header}".').format(header=self.verbose_name))

    def clean(self, value, previous_values):
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        raise NotImplementedError


class EmailColumn(ImportColumn):
    identifier = 'email'
    verbose_name = gettext_lazy('E-mail address')

    def clean(self, value, previous_values):
        if value:
            EmailValidator()(value)
        return value

    def assign(self, value, order, position, invoice_address, **kwargs):
        order.email = value


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
            if str(p.pk) == value or (p.internal_name and p.internal_name == value) or any((v and v == value) for v in p.name.data.values())
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
                if str(p.pk) == value or any((v and v == value) for v in p.value.data.values()) and p.item_id == previous_values['item'].pk
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
        return guess_country(self.event)

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
            return match[0]

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

    def clean(self, value, previous_values):
        if value and OrderPosition.all.filter(order__event=self.event, secret=value).exists():
            raise ValidationError(
                _('You cannot assign a position secret that already exists.')
            )
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
        return self.event.settings.locale

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
            if isinstance(value, QuestionOption):
                a = position.answers.create(question=self.q, answer=str(value))
                a.options.add(value)
            elif isinstance(value, list):
                a = position.answers.create(question=self.q, answer=', '.join(str(v) for v in value))
                a.options.add(*value)
            else:
                position.answers.create(question=self.q, answer=str(value))


def get_all_columns(event):
    default = [
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
        Comment(event)
    ]
    for q in event.questions.exclude(type='F'):
        default.append(QuestionColumn(event, q))

    # TODO: seat
    # TODO: subevent
    # TODO: plugins

    return default


def parse_csv(file, length=None):
    data = file.read(length)
    try:
        import chardet
        charset = chardet.detect(data)['encoding']
    except ImportError:
        charset = file.charset
    data = data.decode(charset or 'utf-8')
    # If the file was modified on a Mac, it only contains \r as line breaks
    if '\r' in data and '\n' not in data:
        data = data.replace('\r', '\n')

    dialect = csv.Sniffer().sniff(data, delimiters=";,.#:")
    if dialect is None:
        return None

    reader = csv.DictReader(io.StringIO(data), dialect=dialect)
    return reader


def setif(record, obj, attr, setting):
    if setting.startswith('csv:'):
        setattr(obj, attr, record[setting[4:]] or '')


@app.task(base=ProfiledEventTask, throws=(DataImportError,))
def import_orders(event: Event, fileid: str, settings: dict, locale: str, user) -> None:
    # TODO: quotacheck?
    cf = CachedFile.objects.get(id=fileid)
    user = User.objects.get(pk=user)
    with language(locale):
        cols = get_all_columns(event)
        parsed = parse_csv(cf.file)
        orders = []
        order = None
        data = []

        # Run validation
        for i, record in enumerate(parsed):
            values = {}
            for c in cols:
                val = c.resolve(settings, record)
                try:
                    values[c.identifier] = c.clean(val, values)
                except ValidationError as e:
                    raise DataImportError(
                        _(
                            'Error while importing value "{value}" for column "{column}" in line "{line}": {message}').format(
                            value=val if val is not None else '', column=c.verbose_name, line=i + 1, message=e.message
                        )
                    )
            data.append(values)

        # Prepare model objects. Yes, this might consume lots of RAM, but allows us to make the actual SQL transaction
        # shorter. We'll see what works better in reality…
        for i, record in enumerate(data):
            try:
                if order is None or settings['orders'] == 'many':
                    order = Order(
                        event=event,
                        testmode=settings['testmode'],
                    )
                    order.meta_info = {}
                    order._positions = []
                    order._address = InvoiceAddress()
                    order._address.name_parts = {'_scheme': event.settings.name_scheme}
                    orders.append(order)

                position = OrderPosition()
                position.attendee_name_parts = {'_scheme': event.settings.name_scheme}
                position.meta_info = {}
                order._positions.append(position)
                position.assign_pseudonymization_id()

                for c in cols:
                    c.assign(record.get(c.identifier), order, position, order._address)

            except ImportError as e:
                raise ImportError(
                    _('Invalid data in row {row}: {message}').format(row=i, message=str(e))
                )

        # quota check?
        with event.lock():
            with transaction.atomic():
                for o in orders:
                    o.total = sum([c.price for c in o._positions])  # currently no support for fees
                    if o.total == Decimal('0.00'):
                        o.status = Order.STATUS_PAID
                        o.save()
                        OrderPayment.objects.create(
                            local_id=1,
                            order=o,
                            amount=Decimal('0.00'),
                            provider='free',
                            info='{}',
                            payment_date=now(),
                            state=OrderPayment.PAYMENT_STATE_CONFIRMED
                        )
                    elif settings['status'] == 'paid':
                        o.status = Order.STATUS_PAID
                        o.save()
                        OrderPayment.objects.create(
                            local_id=1,
                            order=o,
                            amount=o.total,
                            provider='manual',
                            info='{}',
                            payment_date=now(),
                            state=OrderPayment.PAYMENT_STATE_CONFIRMED
                        )
                    else:
                        o.status = Order.STATUS_PENDING
                        o.save()
                    for p in o._positions:
                        p.order = o
                        p.save()
                    o._address.order = o
                    o._address.save()
                    o.log_action(
                        'pretix.event.order.placed',
                        user=user,
                        data={'source': 'import'}
                    )

            for o in orders:
                with language(o.locale):
                    order_placed.send(event, order=o)
                    if o.status == Order.STATUS_PAID:
                        order_paid.send(event, order=o)

                    gen_invoice = invoice_qualified(o) and (
                        (event.settings.get('invoice_generate') == 'True') or
                        (event.settings.get('invoice_generate') == 'paid' and o.status == Order.STATUS_PAID)
                    ) and not o.invoices.last()
                    if gen_invoice:
                        generate_invoice(o, trigger_pdf=True)
    cf.delete()
