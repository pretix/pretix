import csv
import io
from collections import OrderedDict
from decimal import Decimal

import pytz
from django import forms
from django.db.models import Sum
from django.dispatch import receiver
from django.utils.formats import localize
from django.utils.translation import ugettext as _

from pretix.base.models import InvoiceAddress, Order, OrderPosition

from ..exporter import BaseExporter
from ..signals import register_data_exporters, register_payment_providers


class OrderListExporter(BaseExporter):
    identifier = 'orderlistcsv'
    verbose_name = _('List of orders (CSV)')

    @property
    def export_form_fields(self):
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
            qs.exclude(payment_fee=0).values_list('payment_fee_tax_rate', flat=True)
              .distinct().order_by()
        )
        tax_rates |= set(
            a for a
            in OrderPosition.objects.filter(order__event=self.event)
                                    .values_list('tax_rate', flat=True).distinct().order_by()
        )
        tax_rates = sorted(tax_rates)
        return tax_rates

    def render(self, form_data: dict):
        output = io.StringIO()
        tz = pytz.timezone(self.event.settings.timezone)
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        qs = self.event.orders.all().select_related('invoice_address').prefetch_related('invoices')
        if form_data['paid_only']:
            qs = qs.filter(status=Order.STATUS_PAID)
        tax_rates = self._get_all_tax_rates(qs)

        headers = [
            _('Order code'), _('Order total'), _('Status'), _('Email'), _('Order date'),
            _('Company'), _('Name'), _('Address'), _('ZIP code'), _('City'), _('Country'), _('VAT ID'),
            _('Payment date'), _('Payment type'), _('Payment method fee'), _('Invoice numbers')
        ]

        for tr in tax_rates:
            headers += [
                _('Gross at {rate} % tax').format(rate=tr),
                _('Net at {rate} % tax').format(rate=tr),
                _('Tax value at {rate} % tax').format(rate=tr),
            ]

        writer.writerow(headers)

        provider_names = {}
        responses = register_payment_providers.send(self.event)
        for rec, response in responses:
            provider = response(self.event)
            provider_names[provider.identifier] = provider.verbose_name

        sum_cache = {
            (o['order__id'], o['tax_rate']): o for o in
            OrderPosition.objects.values('tax_rate', 'order__id').order_by().annotate(
                taxsum=Sum('tax_value'), grosssum=Sum('price')
            )
        }

        for order in qs.order_by('datetime'):
            row = [
                order.code,
                localize(order.total),
                order.get_status_display(),
                order.email,
                order.datetime.astimezone(tz).strftime('%Y-%m-%d'),
            ]
            try:
                row += [
                    order.invoice_address.company,
                    order.invoice_address.name,
                    order.invoice_address.street,
                    order.invoice_address.zipcode,
                    order.invoice_address.city,
                    order.invoice_address.country,
                    order.invoice_address.vat_id,
                ]
            except InvoiceAddress.DoesNotExist:
                row += ['', '', '', '', '', '', '']

            row += [
                order.payment_date.astimezone(tz).strftime('%Y-%m-%d') if order.payment_date else '',
                provider_names.get(order.payment_provider, order.payment_provider),
                localize(order.payment_fee)
            ]

            for tr in tax_rates:
                taxrate_values = sum_cache.get((order.id, tr), {'grosssum': Decimal('0.00'), 'taxsum': Decimal('0.00')})
                if tr == order.payment_fee_tax_rate and order.payment_fee_tax_value:
                    taxrate_values['grosssum'] += order.payment_fee
                    taxrate_values['taxsum'] += order.payment_fee_tax_value

                row += [
                    localize(taxrate_values['grosssum']),
                    localize(taxrate_values['grosssum'] - taxrate_values['taxsum']),
                    localize(taxrate_values['taxsum']),
                ]

            row.append(', '.join([i.number for i in order.invoices.all()]))
            writer.writerow(row)

        return 'orders.csv', 'text/csv', output.getvalue().encode("utf-8")


@receiver(register_data_exporters, dispatch_uid="exporter_orderlist")
def register_orderlist_exporter(sender, **kwargs):
    return OrderListExporter
