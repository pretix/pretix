from collections import OrderedDict
from decimal import Decimal

import pytz
from django import forms
from django.db.models import (
    Count, DateTimeField, F, IntegerField, Max, OuterRef, Subquery, Sum,
)
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.translation import gettext as _, gettext_lazy, pgettext

from pretix.base.models import (
    GiftCard, Invoice, InvoiceAddress, InvoiceLine, Order, OrderPosition,
    Question,
)
from pretix.base.models.orders import OrderFee, OrderPayment, OrderRefund
from pretix.base.services.quotas import QuotaAvailability
from pretix.base.settings import PERSON_NAME_SCHEMES

from ...control.forms.filter import get_all_payment_providers
from ..exporter import ListExporter, MultiSheetListExporter
from ..signals import (
    register_data_exporters, register_multievent_data_exporters,
)


class OrderListExporter(MultiSheetListExporter):
    identifier = 'orderlist'
    verbose_name = gettext_lazy('Order data')

    @property
    def sheets(self):
        return (
            ('orders', _('Orders')),
            ('positions', _('Order positions')),
            ('fees', _('Order fees')),
        )

    @property
    def additional_form_fields(self):
        return OrderedDict(
            [
                ('paid_only',
                 forms.BooleanField(
                     label=_('Only paid orders'),
                     initial=True,
                     required=False
                 )),
            ]
        )

    def _get_all_tax_rates(self, qs):
        tax_rates = set(
            a for a
            in OrderFee.objects.filter(
                order__event__in=self.events
            ).values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates |= set(
            a for a
            in OrderPosition.objects.filter(
                order__event__in=self.events
            ).values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates = sorted(tax_rates)
        return tax_rates

    def iterate_sheet(self, form_data, sheet):
        if sheet == 'orders':
            return self.iterate_orders(form_data)
        elif sheet == 'positions':
            return self.iterate_positions(form_data)
        elif sheet == 'fees':
            return self.iterate_fees(form_data)

    def iterate_orders(self, form_data: dict):
        p_date = OrderPayment.objects.filter(
            order=OuterRef('pk'),
            state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED),
            payment_date__isnull=False
        ).values('order').annotate(
            m=Max('payment_date')
        ).values(
            'm'
        ).order_by()

        s = OrderPosition.objects.filter(
            order=OuterRef('pk')
        ).order_by().values('order').annotate(k=Count('id')).values('k')
        qs = Order.objects.filter(event__in=self.events).annotate(
            payment_date=Subquery(p_date, output_field=DateTimeField()),
            pcnt=Subquery(s, output_field=IntegerField())
        ).select_related('invoice_address').prefetch_related('invoices').prefetch_related('event')
        if form_data['paid_only']:
            qs = qs.filter(status=Order.STATUS_PAID)
        tax_rates = self._get_all_tax_rates(qs)

        headers = [
            _('Event slug'), _('Order code'), _('Order total'), _('Status'), _('Email'), _('Order date'),
            _('Company'), _('Name'),
        ]
        name_scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme] if not self.is_multievent else None
        if name_scheme and len(name_scheme['fields']) > 1:
            for k, label, w in name_scheme['fields']:
                headers.append(label)
        headers += [
            _('Address'), _('ZIP code'), _('City'), _('Country'), pgettext('address', 'State'), _('VAT ID'),
            _('Date of last payment'), _('Fees'), _('Order locale')
        ]

        for tr in tax_rates:
            headers += [
                _('Gross at {rate} % tax').format(rate=tr),
                _('Net at {rate} % tax').format(rate=tr),
                _('Tax value at {rate} % tax').format(rate=tr),
            ]

        headers.append(_('Invoice numbers'))
        headers.append(_('Sales channel'))
        headers.append(_('Requires special attention'))
        headers.append(_('Comment'))
        headers.append(_('Positions'))

        yield headers

        full_fee_sum_cache = {
            o['order__id']: o['grosssum'] for o in
            OrderFee.objects.values('tax_rate', 'order__id').order_by().annotate(grosssum=Sum('value'))
        }
        fee_sum_cache = {
            (o['order__id'], o['tax_rate']): o for o in
            OrderFee.objects.values('tax_rate', 'order__id').order_by().annotate(
                taxsum=Sum('tax_value'), grosssum=Sum('value')
            )
        }
        sum_cache = {
            (o['order__id'], o['tax_rate']): o for o in
            OrderPosition.objects.values('tax_rate', 'order__id').order_by().annotate(
                taxsum=Sum('tax_value'), grosssum=Sum('price')
            )
        }

        for order in qs.order_by('datetime'):
            tz = pytz.timezone(order.event.settings.timezone)

            row = [
                order.event.slug,
                order.code,
                order.total,
                order.get_status_display(),
                order.email,
                order.datetime.astimezone(tz).strftime('%Y-%m-%d'),
            ]
            try:
                row += [
                    order.invoice_address.company,
                    order.invoice_address.name,
                ]
                if name_scheme and len(name_scheme['fields']) > 1:
                    for k, label, w in name_scheme['fields']:
                        row.append(
                            order.invoice_address.name_parts.get(k, '')
                        )
                row += [
                    order.invoice_address.street,
                    order.invoice_address.zipcode,
                    order.invoice_address.city,
                    order.invoice_address.country if order.invoice_address.country else
                    order.invoice_address.country_old,
                    order.invoice_address.state,
                    order.invoice_address.vat_id,
                ]
            except InvoiceAddress.DoesNotExist:
                row += [''] * (8 + (len(name_scheme['fields']) if name_scheme and len(name_scheme['fields']) > 1 else 0))

            row += [
                order.payment_date.astimezone(tz).strftime('%Y-%m-%d') if order.payment_date else '',
                full_fee_sum_cache.get(order.id) or Decimal('0.00'),
                order.locale,
            ]

            for tr in tax_rates:
                taxrate_values = sum_cache.get((order.id, tr), {'grosssum': Decimal('0.00'), 'taxsum': Decimal('0.00')})
                fee_taxrate_values = fee_sum_cache.get((order.id, tr),
                                                       {'grosssum': Decimal('0.00'), 'taxsum': Decimal('0.00')})

                row += [
                    taxrate_values['grosssum'] + fee_taxrate_values['grosssum'],
                    (
                        taxrate_values['grosssum'] - taxrate_values['taxsum'] +
                        fee_taxrate_values['grosssum'] - fee_taxrate_values['taxsum']
                    ),
                    taxrate_values['taxsum'] + fee_taxrate_values['taxsum'],
                ]

            row.append(', '.join([i.number for i in order.invoices.all()]))
            row.append(order.sales_channel)
            row.append(_('Yes') if order.checkin_attention else _('No'))
            row.append(order.comment or "")
            row.append(order.pcnt)
            yield row

    def iterate_fees(self, form_data: dict):
        qs = OrderFee.objects.filter(
            order__event__in=self.events,
        ).select_related('order', 'order__invoice_address', 'tax_rule')
        if form_data['paid_only']:
            qs = qs.filter(order__status=Order.STATUS_PAID)

        headers = [
            _('Event slug'),
            _('Order code'),
            _('Status'),
            _('Email'),
            _('Order date'),
            _('Fee type'),
            _('Description'),
            _('Price'),
            _('Tax rate'),
            _('Tax rule'),
            _('Tax value'),
            _('Company'),
            _('Invoice address name'),
        ]
        name_scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme] if not self.is_multievent else None
        if name_scheme and len(name_scheme['fields']) > 1:
            for k, label, w in name_scheme['fields']:
                headers.append(_('Invoice address name') + ': ' + str(label))
        headers += [
            _('Address'), _('ZIP code'), _('City'), _('Country'), pgettext('address', 'State'), _('VAT ID'),
        ]

        yield headers

        for op in qs.order_by('order__datetime'):
            order = op.order
            tz = pytz.timezone(order.event.settings.timezone)
            row = [
                order.event.slug,
                order.code,
                order.get_status_display(),
                order.email,
                order.datetime.astimezone(tz).strftime('%Y-%m-%d'),
                op.get_fee_type_display(),
                op.description,
                op.value,
                op.tax_rate,
                str(op.tax_rule) if op.tax_rule else '',
                op.tax_value,
            ]
            try:
                row += [
                    order.invoice_address.company,
                    order.invoice_address.name,
                ]
                if name_scheme and len(name_scheme['fields']) > 1:
                    for k, label, w in name_scheme['fields']:
                        row.append(
                            order.invoice_address.name_parts.get(k, '')
                        )
                row += [
                    order.invoice_address.street,
                    order.invoice_address.zipcode,
                    order.invoice_address.city,
                    order.invoice_address.country if order.invoice_address.country else
                    order.invoice_address.country_old,
                    order.invoice_address.state,
                    order.invoice_address.vat_id,
                ]
            except InvoiceAddress.DoesNotExist:
                row += [''] * (8 + (len(name_scheme['fields']) if name_scheme and len(name_scheme['fields']) > 1 else 0))
            yield row

    def iterate_positions(self, form_data: dict):
        qs = OrderPosition.objects.filter(
            order__event__in=self.events,
        ).select_related(
            'order', 'order__invoice_address', 'item', 'variation',
            'voucher', 'tax_rule'
        ).prefetch_related(
            'answers', 'answers__question', 'answers__options'
        )
        if form_data['paid_only']:
            qs = qs.filter(order__status=Order.STATUS_PAID)

        headers = [
            _('Event slug'),
            _('Order code'),
            _('Position ID'),
            _('Status'),
            _('Email'),
            _('Order date'),
        ]
        if self.events.filter(has_subevents=True).exists():
            headers.append(pgettext('subevent', 'Date'))
            headers.append(_('Start date'))
            headers.append(_('End date'))
        headers += [
            _('Product'),
            _('Variation'),
            _('Price'),
            _('Tax rate'),
            _('Tax rule'),
            _('Tax value'),
            _('Attendee name'),
        ]
        name_scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme] if not self.is_multievent else None
        if name_scheme and len(name_scheme['fields']) > 1:
            for k, label, w in name_scheme['fields']:
                headers.append(_('Attendee name') + ': ' + str(label))
        headers += [
            _('Attendee email'),
            _('Company'),
            _('Address'),
            _('ZIP code'),
            _('City'),
            _('Country'),
            pgettext('address', 'State'),
            _('Voucher'),
            _('Pseudonymization ID'),
        ]

        questions = list(Question.objects.filter(event__in=self.events))
        options = {}
        for q in questions:
            if q.type == Question.TYPE_CHOICE_MULTIPLE:
                options[q.pk] = []
                for o in q.options.all():
                    headers.append(str(q.question) + ' – ' + str(o.answer))
                    options[q.pk].append(o)
            else:
                headers.append(str(q.question))
        headers += [
            _('Company'),
            _('Invoice address name'),
        ]
        if name_scheme and len(name_scheme['fields']) > 1:
            for k, label, w in name_scheme['fields']:
                headers.append(_('Invoice address name') + ': ' + str(label))
        headers += [
            _('Address'), _('ZIP code'), _('City'), _('Country'), pgettext('address', 'State'), _('VAT ID'),
        ]
        headers += [
            _('Sales channel'), _('Order locale'),
        ]

        yield headers

        for op in qs.order_by('order__datetime', 'positionid'):
            order = op.order
            tz = pytz.timezone(order.event.settings.timezone)
            row = [
                order.event.slug,
                order.code,
                op.positionid,
                order.get_status_display(),
                order.email,
                order.datetime.astimezone(tz).strftime('%Y-%m-%d'),
            ]
            if order.event.has_subevents:
                row.append(op.subevent.name)
                row.append(op.subevent.date_from.astimezone(order.event.timezone).strftime('%Y-%m-%d %H:%M:%S'))
                if op.subevent.date_to:
                    row.append(op.subevent.date_to.astimezone(order.event.timezone).strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    row.append('')
            row += [
                str(op.item),
                str(op.variation) if op.variation else '',
                op.price,
                op.tax_rate,
                str(op.tax_rule) if op.tax_rule else '',
                op.tax_value,
                op.attendee_name,
            ]
            if name_scheme and len(name_scheme['fields']) > 1:
                for k, label, w in name_scheme['fields']:
                    row.append(
                        op.attendee_name_parts.get(k, '')
                    )
            row += [
                op.attendee_email,
                op.company or '',
                op.street or '',
                op.zipcode or '',
                op.city or '',
                op.country if op.country else '',
                op.state or '',
                op.voucher.code if op.voucher else '',
                op.pseudonymization_id,
            ]
            acache = {}
            for a in op.answers.all():
                # We do not want to localize Date, Time and Datetime question answers, as those can lead
                # to difficulties parsing the data (for example 2019-02-01 may become Février, 2019 01 in French).
                if a.question.type == Question.TYPE_CHOICE_MULTIPLE:
                    acache[a.question_id] = set(o.pk for o in a.options.all())
                elif a.question.type in Question.UNLOCALIZED_TYPES:
                    acache[a.question_id] = a.answer
                else:
                    acache[a.question_id] = str(a)
            for q in questions:
                if q.type == Question.TYPE_CHOICE_MULTIPLE:
                    for o in options[q.pk]:
                        row.append(_('Yes') if o.pk in acache.get(q.pk, set()) else _('No'))
                else:
                    row.append(acache.get(q.pk, ''))

            try:
                row += [
                    order.invoice_address.company,
                    order.invoice_address.name,
                ]
                if name_scheme and len(name_scheme['fields']) > 1:
                    for k, label, w in name_scheme['fields']:
                        row.append(
                            order.invoice_address.name_parts.get(k, '')
                        )
                row += [
                    order.invoice_address.street,
                    order.invoice_address.zipcode,
                    order.invoice_address.city,
                    order.invoice_address.country if order.invoice_address.country else
                    order.invoice_address.country_old,
                    order.invoice_address.state,
                    order.invoice_address.vat_id,
                ]
            except InvoiceAddress.DoesNotExist:
                row += [''] * (8 + (len(name_scheme['fields']) if name_scheme and len(name_scheme['fields']) > 1 else 0))
            row += [
                order.sales_channel,
                order.locale
            ]
            yield row

    def get_filename(self):
        if self.is_multievent:
            return '{}_orders'.format(self.events.first().organizer.slug)
        else:
            return '{}_orders'.format(self.event.slug)


class PaymentListExporter(ListExporter):
    identifier = 'paymentlist'
    verbose_name = gettext_lazy('Order payments and refunds')

    @property
    def additional_form_fields(self):
        return OrderedDict(
            [
                ('payment_states',
                 forms.MultipleChoiceField(
                     label=_('Payment states'),
                     choices=OrderPayment.PAYMENT_STATES,
                     initial=[OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED],
                     required=False,
                     widget=forms.CheckboxSelectMultiple,
                 )),
                ('refund_states',
                 forms.MultipleChoiceField(
                     label=_('Refund states'),
                     choices=OrderRefund.REFUND_STATES,
                     initial=[OrderRefund.REFUND_STATE_DONE, OrderRefund.REFUND_STATE_CREATED,
                              OrderRefund.REFUND_STATE_TRANSIT],
                     widget=forms.CheckboxSelectMultiple,
                     required=False
                 )),
            ]
        )

    def iterate_list(self, form_data):
        provider_names = dict(get_all_payment_providers())

        payments = OrderPayment.objects.filter(
            order__event__in=self.events,
            state__in=form_data.get('payment_states', [])
        ).order_by('created')
        refunds = OrderRefund.objects.filter(
            order__event__in=self.events,
            state__in=form_data.get('refund_states', [])
        ).order_by('created')

        objs = sorted(list(payments) + list(refunds), key=lambda o: o.created)

        headers = [
            _('Event slug'), _('Order'), _('Payment ID'), _('Creation date'), _('Completion date'), _('Status'),
            _('Status code'), _('Amount'), _('Payment method')
        ]
        yield headers

        for obj in objs:
            tz = pytz.timezone(obj.order.event.settings.timezone)
            if isinstance(obj, OrderPayment) and obj.payment_date:
                d2 = obj.payment_date.astimezone(tz).date().strftime('%Y-%m-%d')
            elif isinstance(obj, OrderRefund) and obj.execution_date:
                d2 = obj.execution_date.astimezone(tz).date().strftime('%Y-%m-%d')
            else:
                d2 = ''
            row = [
                obj.order.event.slug,
                obj.order.code,
                obj.full_id,
                obj.created.astimezone(tz).date().strftime('%Y-%m-%d'),
                d2,
                obj.get_state_display(),
                obj.state,
                obj.amount * (-1 if isinstance(obj, OrderRefund) else 1),
                provider_names.get(obj.provider, obj.provider)
            ]
            yield row

    def get_filename(self):
        if self.is_multievent:
            return '{}_payments'.format(self.events.first().organizer.slug)
        else:
            return '{}_payments'.format(self.event.slug)


class QuotaListExporter(ListExporter):
    identifier = 'quotalist'
    verbose_name = gettext_lazy('Quota availabilities')

    def iterate_list(self, form_data):
        headers = [
            _('Quota name'), _('Total quota'), _('Paid orders'), _('Pending orders'), _('Blocking vouchers'),
            _('Current user\'s carts'), _('Waiting list'), _('Current availability')
        ]
        yield headers

        quotas = list(self.event.quotas.all())
        qa = QuotaAvailability(full_results=True)
        qa.queue(*quotas)
        qa.compute()

        for quota in quotas:
            avail = qa.results[quota]
            row = [
                quota.name,
                _('Infinite') if quota.size is None else quota.size,
                qa.count_paid_orders[quota],
                qa.count_pending_orders[quota],
                qa.count_vouchers[quota],
                qa.count_cart[quota],
                qa.count_waitinglist[quota],
                _('Infinite') if avail[1] is None else avail[1]
            ]
            yield row

    def get_filename(self):
        return '{}_quotas'.format(self.event.slug)


class InvoiceDataExporter(MultiSheetListExporter):
    identifier = 'invoicedata'
    verbose_name = gettext_lazy('Invoice data')

    @property
    def sheets(self):
        return (
            ('invoices', _('Invoices')),
            ('lines', _('Invoice lines')),
        )

    def iterate_sheet(self, form_data, sheet):
        if sheet == 'invoices':
            yield [
                _('Invoice number'),
                _('Date'),
                _('Order code'),
                _('E-mail address'),
                _('Invoice type'),
                _('Cancellation of'),
                _('Language'),
                _('Invoice sender:') + ' ' + _('Name'),
                _('Invoice sender:') + ' ' + _('Address'),
                _('Invoice sender:') + ' ' + _('ZIP code'),
                _('Invoice sender:') + ' ' + _('City'),
                _('Invoice sender:') + ' ' + _('Country'),
                _('Invoice sender:') + ' ' + _('Tax ID'),
                _('Invoice sender:') + ' ' + _('VAT ID'),
                _('Invoice recipient:') + ' ' + _('Company'),
                _('Invoice recipient:') + ' ' + _('Name'),
                _('Invoice recipient:') + ' ' + _('Street address'),
                _('Invoice recipient:') + ' ' + _('ZIP code'),
                _('Invoice recipient:') + ' ' + _('City'),
                _('Invoice recipient:') + ' ' + _('Country'),
                _('Invoice recipient:') + ' ' + pgettext('address', 'State'),
                _('Invoice recipient:') + ' ' + _('VAT ID'),
                _('Invoice recipient:') + ' ' + _('Beneficiary'),
                _('Invoice recipient:') + ' ' + _('Internal reference'),
                _('Reverse charge'),
                _('Shown foreign currency'),
                _('Foreign currency rate'),
                _('Total value (with taxes)'),
                _('Total value (without taxes)'),
                _('Payment matching IDs'),
            ]
            qs = Invoice.objects.filter(event__in=self.events).order_by('full_invoice_no').select_related(
                'order', 'refers'
            ).prefetch_related('order__payments').annotate(
                total_gross=Subquery(
                    InvoiceLine.objects.filter(
                        invoice=OuterRef('pk')
                    ).order_by().values('invoice').annotate(
                        s=Sum('gross_value')
                    ).values('s')
                ),
                total_net=Subquery(
                    InvoiceLine.objects.filter(
                        invoice=OuterRef('pk')
                    ).order_by().values('invoice').annotate(
                        s=Sum(F('gross_value') - F('tax_value'))
                    ).values('s')
                )
            )
            for i in qs:
                pmis = []
                for p in i.order.payments.all():
                    if p.state in (OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_CREATED,
                                   OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_REFUNDED):
                        pprov = p.payment_provider
                        if pprov:
                            mid = pprov.matching_id(p)
                            if mid:
                                pmis.append(mid)
                pmi = '\n'.join(pmis)
                yield [
                    i.full_invoice_no,
                    date_format(i.date, "SHORT_DATE_FORMAT"),
                    i.order.code,
                    i.order.email,
                    _('Cancellation') if i.is_cancellation else _('Invoice'),
                    i.refers.full_invoice_no if i.refers else '',
                    i.locale,
                    i.invoice_from_name,
                    i.invoice_from,
                    i.invoice_from_zipcode,
                    i.invoice_from_city,
                    i.invoice_from_country,
                    i.invoice_from_tax_id,
                    i.invoice_from_vat_id,
                    i.invoice_to_company,
                    i.invoice_to_name,
                    i.invoice_to_street or i.invoice_to,
                    i.invoice_to_zipcode,
                    i.invoice_to_city,
                    i.invoice_to_country,
                    i.invoice_to_state,
                    i.invoice_to_vat_id,
                    i.invoice_to_beneficiary,
                    i.internal_reference,
                    _('Yes') if i.reverse_charge else _('No'),
                    i.foreign_currency_display,
                    i.foreign_currency_rate,
                    i.total_gross if i.total_gross else Decimal('0.00'),
                    Decimal(i.total_net if i.total_net else '0.00').quantize(Decimal('0.01')),
                    pmi
                ]
        elif sheet == 'lines':
            yield [
                _('Invoice number'),
                _('Line number'),
                _('Description'),
                _('Gross price'),
                _('Net price'),
                _('Tax value'),
                _('Tax rate'),
                _('Tax name'),
                _('Event start date'),

                _('Date'),
                _('Order code'),
                _('E-mail address'),
                _('Invoice type'),
                _('Cancellation of'),
                _('Invoice sender:') + ' ' + _('Name'),
                _('Invoice sender:') + ' ' + _('Address'),
                _('Invoice sender:') + ' ' + _('ZIP code'),
                _('Invoice sender:') + ' ' + _('City'),
                _('Invoice sender:') + ' ' + _('Country'),
                _('Invoice sender:') + ' ' + _('Tax ID'),
                _('Invoice sender:') + ' ' + _('VAT ID'),
                _('Invoice recipient:') + ' ' + _('Company'),
                _('Invoice recipient:') + ' ' + _('Name'),
                _('Invoice recipient:') + ' ' + _('Street address'),
                _('Invoice recipient:') + ' ' + _('ZIP code'),
                _('Invoice recipient:') + ' ' + _('City'),
                _('Invoice recipient:') + ' ' + _('Country'),
                _('Invoice recipient:') + ' ' + pgettext('address', 'State'),
                _('Invoice recipient:') + ' ' + _('VAT ID'),
                _('Invoice recipient:') + ' ' + _('Beneficiary'),
                _('Invoice recipient:') + ' ' + _('Internal reference'),
            ]
            qs = InvoiceLine.objects.filter(
                invoice__event__in=self.events
            ).order_by('invoice__full_invoice_no', 'position').select_related(
                'invoice', 'invoice__order', 'invoice__refers'
            )
            for l in qs:
                i = l.invoice
                yield [
                    i.full_invoice_no,
                    l.position + 1,
                    l.description.replace("<br />", " - "),
                    l.gross_value,
                    l.net_value,
                    l.tax_value,
                    l.tax_rate,
                    l.tax_name,
                    date_format(l.event_date_from, "SHORT_DATE_FORMAT") if l.event_date_from else "",
                    date_format(i.date, "SHORT_DATE_FORMAT"),
                    i.order.code,
                    i.order.email,
                    _('Cancellation') if i.is_cancellation else _('Invoice'),
                    i.refers.full_invoice_no if i.refers else '',
                    i.invoice_from_name,
                    i.invoice_from,
                    i.invoice_from_zipcode,
                    i.invoice_from_city,
                    i.invoice_from_country,
                    i.invoice_from_tax_id,
                    i.invoice_from_vat_id,
                    i.invoice_to_company,
                    i.invoice_to_name,
                    i.invoice_to_street or i.invoice_to,
                    i.invoice_to_zipcode,
                    i.invoice_to_city,
                    i.invoice_to_country,
                    i.invoice_to_state,
                    i.invoice_to_vat_id,
                    i.invoice_to_beneficiary,
                    i.internal_reference,
                ]

    def get_filename(self):
        if self.is_multievent:
            return '{}_invoices'.format(self.events.first().organizer.slug)
        else:
            return '{}_invoices'.format(self.event.slug)


class GiftcardRedemptionListExporter(ListExporter):
    identifier = 'giftcardredemptionlist'
    verbose_name = gettext_lazy('Gift card redemptions')

    def iterate_list(self, form_data):
        payments = OrderPayment.objects.filter(
            order__event__in=self.events,
            provider='giftcard'
        ).order_by('created')
        refunds = OrderRefund.objects.filter(
            order__event__in=self.events,
            provider='giftcard'
        ).order_by('created')

        objs = sorted(list(payments) + list(refunds), key=lambda o: (o.order.code, o.created))

        headers = [
            _('Event slug'), _('Order'), _('Payment ID'), _('Date'), _('Gift card code'), _('Amount'), _('Issuer')
        ]
        yield headers

        for obj in objs:
            tz = pytz.timezone(obj.order.event.settings.timezone)
            gc = GiftCard.objects.get(pk=obj.info_data.get('gift_card'))
            row = [
                obj.order.event.slug,
                obj.order.code,
                obj.full_id,
                obj.created.astimezone(tz).date().strftime('%Y-%m-%d'),
                gc.secret,
                obj.amount * (-1 if isinstance(obj, OrderRefund) else 1),
                gc.issuer
            ]
            yield row

    def get_filename(self):
        if self.is_multievent:
            return '{}_giftcardredemptions'.format(self.events.first().organizer.slug)
        else:
            return '{}_giftcardredemptions'.format(self.event.slug)


@receiver(register_data_exporters, dispatch_uid="exporter_orderlist")
def register_orderlist_exporter(sender, **kwargs):
    return OrderListExporter


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_orderlist")
def register_multievent_orderlist_exporter(sender, **kwargs):
    return OrderListExporter


@receiver(register_data_exporters, dispatch_uid="exporter_paymentlist")
def register_paymentlist_exporter(sender, **kwargs):
    return PaymentListExporter


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_paymentlist")
def register_multievent_paymentlist_exporter(sender, **kwargs):
    return PaymentListExporter


@receiver(register_data_exporters, dispatch_uid="exporter_quotalist")
def register_quotalist_exporter(sender, **kwargs):
    return QuotaListExporter


@receiver(register_data_exporters, dispatch_uid="exporter_invoicedata")
def register_invoicedata_exporter(sender, **kwargs):
    return InvoiceDataExporter


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_invoicedata")
def register_multievent_invoicedatae_xporter(sender, **kwargs):
    return InvoiceDataExporter


@receiver(register_data_exporters, dispatch_uid="exporter_giftcardredemptionlist")
def register_giftcardredemptionlist_exporter(sender, **kwargs):
    return GiftcardRedemptionListExporter


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_giftcardredemptionlist")
def register_multievent_i_giftcardredemptionlist_exporter(sender, **kwargs):
    return GiftcardRedemptionListExporter
