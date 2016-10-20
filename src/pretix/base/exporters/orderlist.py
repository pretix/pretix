import csv
import io
from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.utils.translation import ugettext as _

from pretix.base.models import InvoiceAddress, Order

from ..exporter import BaseExporter
from ..signals import register_data_exporters


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

    def render(self, form_data: dict):
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        qs = self.event.orders.all().select_related('invoice_address')
        headers = [
            _('Order code'), _('Order total'), _('Status'), _('Email'), _('Order date'),
            _('Company'), _('Name'), _('Address'), _('ZIP code'), _('City'), _('Country'), _('VAT ID')
        ]
        if form_data['paid_only']:
            qs = qs.filter(status=Order.STATUS_PAID)

        writer.writerow(headers)

        for order in qs:
            row = [
                order.code,
                str(order.total),
                order.get_status_display(),
                order.email,
                order.datetime.strftime('%Y-%m-%d'),
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

            writer.writerow(row)

        return 'orders.csv', 'text/csv', output.getvalue().encode("utf-8")


@receiver(register_data_exporters, dispatch_uid="exporter_orderlist")
def register_orderlist_exporter(sender, **kwargs):
    return OrderListExporter
