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
import json
from collections import OrderedDict
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext, gettext_lazy, pgettext_lazy

from pretix.base.i18n import language
from pretix.base.models import Invoice, OrderPayment

from ..exporter import BaseExporter
from ..signals import register_data_exporters
from ..timeframes import DateFrameField, resolve_timeframe_to_dates_inclusive


class DekodiNREIExporter(BaseExporter):
    identifier = 'dekodi_nrei'
    verbose_name = 'dekodi NREI (JSON)'
    category = pgettext_lazy('export_category', 'Invoices')
    description = gettext_lazy("Download invoices in a format that can be used by the dekodi NREI conversion software.")

    # Specification: http://manuals.dekodi.de/nexuspub/schnittstellenbuch/

    def _encode_invoice(self, invoice: Invoice):
        p_last = invoice.order.payments.filter(state=[OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED]).last()
        gross_total = Decimal('0.00')
        net_total = Decimal('0.00')

        positions = []
        for l in invoice.lines.all():
            positions.append({
                'ADes': l.description.replace("<br />", "\n"),
                'ANetA': round(float((-1 if invoice.is_cancellation else 1) * l.net_value), 2),
                'ANo': self.event.slug,
                'AQ': -1 if invoice.is_cancellation else 1,
                'AVatP': round(float(l.tax_rate), 2),
                'DIDt': (l.subevent or invoice.order.event).date_from.isoformat().replace('Z', '+00:00'),
                'PosGrossA': round(float(l.gross_value), 2),
                'PosNetA': round(float(l.net_value), 2),
            })
            gross_total += l.gross_value
            net_total += l.net_value

        payments = []
        paypal_email = None
        for p in invoice.order.payments.filter(
                state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_PENDING,
                           OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_REFUNDED)
        ):
            if p.provider == 'paypal':
                paypal_email = p.info_data.get('payer', {}).get('payer_info', {}).get('email')
                try:
                    ppid = p.info_data['transactions'][0]['related_resources'][0]['sale']['id']
                except:
                    ppid = p.info_data.get('id')
                payments.append({
                    'PTID': '1',
                    'PTN': 'PayPal',
                    'PTNo1': ppid,
                    'PTNo2': p.info_data.get('id'),
                    'PTNo7': round(float(p.amount), 2),
                    'PTNo8': str(self.event.currency),
                    'PTNo11': paypal_email or '',
                    'PTNo15': p.full_id or '',
                })
            elif p.provider == 'banktransfer':
                payments.append({
                    'PTID': '4',
                    'PTN': 'Vorkasse',
                    'PTNo4': p.info_data.get('reference') or p.payment_provider._code(invoice.order),
                    'PTNo7': round(float(p.amount), 2),
                    'PTNo8': str(self.event.currency),
                    'PTNo10': p.info_data.get('payer') or '',
                    'PTNo14': p.info_data.get('date') or '',
                    'PTNo15': p.full_id or '',
                })
            elif p.provider == 'sepadebit':
                with language(invoice.order.locale):
                    payments.append({
                        'PTID': '5',
                        'PTN': 'Lastschrift',
                        'PTNo4': gettext('Event ticket {event}-{code}').format(
                            event=self.event.slug.upper(),
                            code=invoice.order.code
                        ),
                        'PTNo5': p.info_data.get('iban') or '',
                        'PTNo6': p.info_data.get('bic') or '',
                        'PTNo7': round(float(p.amount), 2),
                        'PTNo8': str(self.event.currency) or '',
                        'PTNo9': p.info_data.get('date') or '',
                        'PTNo10': p.info_data.get('account') or '',
                        'PTNo14': p.info_data.get('reference') or '',
                        'PTNo15': p.full_id or '',
                    })
            elif p.provider and p.provider.startswith('stripe'):
                src = p.info_data.get("source", p.info_data)
                payments.append({
                    'PTID': '81',
                    'PTN': 'Stripe',
                    'PTNo1': p.info_data.get("id") or '',
                    'PTNo5': src.get("card", {}).get("last4") or '',
                    'PTNo7': round(float(p.amount), 2) or '',
                    'PTNo8': str(self.event.currency) or '',
                    'PTNo10': src.get('owner', {}).get('verified_name') or src.get('owner', {}).get('name') or '',
                    'PTNo15': p.full_id or '',
                })
            else:
                payments.append({
                    'PTID': '0',
                    'PTN': p.provider,
                    'PTNo7': round(float(p.amount), 2) or '',
                    'PTNo8': str(self.event.currency) or '',
                    'PTNo15': p.full_id or '',
                })

        payments = [
            {
                k: v for k, v in p.items() if v is not None
            } for p in payments
        ]

        hdr = {
            'C': str(invoice.invoice_to_country) or self.event.settings.invoice_address_from_country,
            'CC': self.event.currency,
            'City': invoice.invoice_to_city,
            'CN': invoice.invoice_to_company,
            'DIC': self.event.settings.invoice_address_from_country,
            # DIC is  a little bit unclean, should be the event location's country
            'DIDt': invoice.order.datetime.isoformat().replace('Z', '+00:00'),
            'DT': '30' if invoice.is_cancellation else '10',
            'EM': invoice.order.email,
            'FamN': invoice.invoice_to_name.rsplit(' ', 1)[-1] if invoice.invoice_to_name else '',
            'FN': (
                invoice.invoice_to_name.rsplit(' ', 1)[0]
                if invoice.invoice_to_name and ' ' in invoice.invoice_to_name else ''
            ),
            'IDt': invoice.date.isoformat() + 'T08:00:00+01:00',
            'INo': invoice.full_invoice_no,
            'IsNet': invoice.reverse_charge,
            'ODt': invoice.order.datetime.isoformat().replace('Z', '+00:00'),
            'OID': invoice.order.code,
            'SID': self.event.slug,
            'SN': str(self.event),
            'Str': invoice.invoice_to_street or '',
            'TGrossA': round(float(gross_total), 2),
            'TNetA': round(float(net_total), 2),
            'TVatA': round(float(gross_total - net_total), 2),
            'VatDp': False,
            'Zip': invoice.invoice_to_zipcode
        }
        if not hdr['FamN'] and not hdr['CN']:
            hdr['CN'] = "Unbekannter Kunde"

        if invoice.refers:
            hdr['PvrINo'] = invoice.refers.full_invoice_no
        if p_last:
            hdr['PmDt'] = p_last.payment_date.isoformat().replace('Z', '+00:00')
        if paypal_email:
            hdr['PPEm'] = paypal_email
        if invoice.invoice_to_vat_id:
            hdr['VatID'] = invoice.invoice_to_vat_id

        return {
            'IsValid': True,
            'Hdr': hdr,
            'InvcPstns': positions,
            'PmIs': payments,
            'ValidationMessage': ''
        }

    def render(self, form_data):
        qs = self.event.invoices.select_related('order').prefetch_related('lines', 'lines__subevent')

        if form_data.get('date_range'):
            d_start, d_end = resolve_timeframe_to_dates_inclusive(now(), form_data['date_range'], self.timezone)
            if d_start:
                qs = qs.filter(date__gte=d_start)
            if d_end:
                qs = qs.filter(date__lte=d_end)

        jo = {
            'Format': 'NREI',
            'Version': '18.10.2.0',
            'SourceSystem': 'pretix',
            'Data': [
                self._encode_invoice(i) for i in qs
            ]
        }
        return '{}_nrei.json'.format(self.event.slug), 'application/json', json.dumps(jo, cls=DjangoJSONEncoder, indent=4)

    @property
    def export_form_fields(self):
        return OrderedDict(
            [
                ('date_range',
                 DateFrameField(
                     label=gettext_lazy('Date range'),
                     include_future_frames=False,
                     required=False,
                     help_text=gettext_lazy('Only include invoices issued in this time frame. Note that the invoice date does '
                                            'not always correspond to the order or payment date.')
                 )),
            ]
        )


@receiver(register_data_exporters, dispatch_uid="exporter_dekodi_nrei")
def register_dekodi_export(sender, **kwargs):
    return DekodiNREIExporter
