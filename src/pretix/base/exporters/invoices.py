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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import os
import tempfile
from collections import OrderedDict
from decimal import Decimal
from zipfile import ZipFile

from django import forms
from django.db.models import CharField, Exists, F, OuterRef, Q, Subquery, Sum
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import (
    gettext, gettext_lazy as _, pgettext, pgettext_lazy,
)

from pretix.base.models import Invoice, InvoiceLine, OrderPayment

from ...control.forms.filter import get_all_payment_providers
from ...helpers import GroupConcat
from ...helpers.iter import chunked_iterable
from ..exporter import BaseExporter, MultiSheetListExporter
from ..services.export import ExportError
from ..services.invoices import invoice_pdf_task
from ..signals import (
    register_data_exporters, register_multievent_data_exporters,
)
from ..timeframes import DateFrameField, resolve_timeframe_to_dates_inclusive


class InvoiceExporterMixin:
    category = pgettext_lazy('export_category', 'Invoices')

    @property
    def invoice_exporter_form_fields(self):
        return OrderedDict(
            [
                ('date_range',
                 DateFrameField(
                     label=_('Date range'),
                     include_future_frames=False,
                     required=False,
                     help_text=_('Only include invoices issued in this time frame. Note that the invoice date does '
                                 'not always correspond to the order or payment date.')
                 )),
                ('payment_provider',
                 forms.ChoiceField(
                     label=_('Payment provider'),
                     choices=[
                         ('', _('All payment providers')),
                     ] + get_all_payment_providers() if self.is_multievent else [
                         ('', _('All payment providers')),
                     ] + [
                         (k, v.verbose_name) for k, v in self.event.get_payment_providers().items()
                     ],
                     required=False,
                     help_text=_('Only include invoices for orders that have at least one payment attempt '
                                 'with this payment provider. '
                                 'Note that this might include some invoices of orders which in the end have been '
                                 'fully or partially paid with a different provider.')
                 )),
            ]
        )

    def invoices_queryset(self, form_data: dict):
        qs = Invoice.objects.filter(event__in=self.events).select_related('order')

        if form_data.get('payment_provider'):
            qs = qs.annotate(
                has_payment_with_provider=Exists(
                    OrderPayment.objects.filter(
                        Q(order=OuterRef('order_id')) & Q(provider=form_data.get('payment_provider')),
                        state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED,
                                   OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED),
                    )
                )
            )
            qs = qs.filter(has_payment_with_provider=1)
        if form_data.get('date_range'):
            d_start, d_end = resolve_timeframe_to_dates_inclusive(now(), form_data['date_range'], self.timezone)
            if d_start:
                qs = qs.filter(date__gte=d_start)
            if d_end:
                qs = qs.filter(date__lte=d_end)

        return qs


class InvoiceExporter(InvoiceExporterMixin, BaseExporter):
    identifier = 'invoices'
    verbose_name = _('All invoices')
    description = _('Download all invoices created by the system as a ZIP file of PDF files.')

    def render(self, form_data: dict, output_file=None):
        qs = self.invoices_queryset(form_data).filter(shredded=False)

        with tempfile.TemporaryDirectory() as d:
            total = qs.count()

            if not total:
                return None

            counter = 0
            with ZipFile(output_file or os.path.join(d, 'tmp.zip'), 'w') as zipf:
                for i in qs.iterator():
                    try:
                        if not i.file:
                            invoice_pdf_task.apply(args=(i.pk,))
                            i.refresh_from_db()
                        if not i.file:
                            raise ExportError('Could not generate PDF for invoice {nr}'.format(nr=i.full_invoice_no))
                        i.file.open('rb')
                        zipf.writestr('{}-{}.pdf'.format(i.number, i.order.code), i.file.read())
                        i.file.close()
                    except FileNotFoundError:
                        invoice_pdf_task.apply(args=(i.pk,))
                        i.refresh_from_db()
                        i.file.open('rb')
                        zipf.writestr('{}-{}.pdf'.format(i.number, i.order.code), i.file.read())
                        i.file.close()
                    counter += 1
                    if total and counter % max(10, total // 100) == 0:
                        self.progress_callback(counter / total * 100)

            if self.is_multievent:
                filename = '{}_invoices.zip'.format(self.organizer.slug)
            else:
                filename = '{}_invoices.zip'.format(self.event.slug)

            if output_file:
                return filename, 'application/zip', None
            else:
                with open(os.path.join(d, 'tmp.zip'), 'rb') as zipf:
                    return filename, 'application/zip', zipf.read()

    @property
    def export_form_fields(self):
        return self.invoice_exporter_form_fields


class InvoiceDataExporter(InvoiceExporterMixin, MultiSheetListExporter):
    identifier = 'invoicedata'
    verbose_name = _('Invoice data')
    description = _('Download a spreadsheet with the data of all invoices created by the system. The spreadsheet '
                    'includes two sheets, one with a line for every invoice, and one with a line for every position of '
                    'every invoice.')
    featured = True

    @property
    def additional_form_fields(self):
        return self.invoice_exporter_form_fields

    @property
    def sheets(self):
        return (
            ('invoices', _('Invoices')),
            ('lines', _('Invoice lines')),
        )

    def iterate_sheet(self, form_data, sheet):
        _ = gettext
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
                _('Payment providers'),
            ]

            p_providers = OrderPayment.objects.filter(
                order=OuterRef('order'),
                state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED,
                           OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED),
            ).values('order').annotate(
                m=GroupConcat('provider', delimiter=',')
            ).values(
                'm'
            ).order_by()

            base_qs = self.invoices_queryset(form_data)\

            qs = base_qs.select_related(
                'order', 'refers'
            ).prefetch_related('order__payments').annotate(
                payment_providers=Subquery(p_providers, output_field=CharField()),
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

            all_ids = base_qs.order_by('full_invoice_no').values_list('pk', flat=True)
            yield self.ProgressSetTotal(total=len(all_ids))
            for ids in chunked_iterable(all_ids, 1000):
                invs = sorted(qs.filter(id__in=ids), key=lambda k: ids.index(k.pk))

                for i in invs:
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
                        pmi,
                        ', '.join([
                            str(self.providers.get(p, p)) for p in sorted(set((i.payment_providers or '').split(',')))
                            if p and p != 'free'
                        ])
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
                _('Payment providers'),
                _('Event end date'),
                _('Location'),
            ]

            p_providers = OrderPayment.objects.filter(
                order=OuterRef('invoice__order'),
                state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED,
                           OrderPayment.PAYMENT_STATE_PENDING, OrderPayment.PAYMENT_STATE_CREATED),
            ).values('order').annotate(
                m=GroupConcat('provider', delimiter=',')
            ).values(
                'm'
            ).order_by()

            qs = InvoiceLine.objects.annotate(
                payment_providers=Subquery(p_providers, output_field=CharField()),
            ).filter(
                invoice__in=self.invoices_queryset(form_data)
            ).order_by('invoice__full_invoice_no', 'position').select_related(
                'invoice', 'invoice__order', 'invoice__refers'
            )
            yield self.ProgressSetTotal(total=qs.count())

            for l in qs.iterator():
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
                    ', '.join([
                        str(self.providers.get(p, p)) for p in sorted(set((l.payment_providers or '').split(',')))
                        if p and p != 'free'
                    ]),
                    date_format(l.event_date_to, "SHORT_DATE_FORMAT") if l.event_date_to else "",
                    l.event_location or "",
                ]

    @cached_property
    def providers(self):
        return dict(get_all_payment_providers())

    def get_filename(self):
        if self.is_multievent:
            return '{}_invoices'.format(self.organizer.slug)
        else:
            return '{}_invoices'.format(self.event.slug)


@receiver(register_data_exporters, dispatch_uid="exporter_invoices")
def register_invoice_export(sender, **kwargs):
    return InvoiceExporter


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_invoices")
def register_multievent_invoice_export(sender, **kwargs):
    return InvoiceExporter


@receiver(register_data_exporters, dispatch_uid="exporter_invoicedata")
def register_invoicedata_exporter(sender, **kwargs):
    return InvoiceDataExporter


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_invoicedata")
def register_multievent_invoicedatae_xporter(sender, **kwargs):
    return InvoiceDataExporter
