from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.utils.translation import ugettext as _

from ..exporter import BaseExporter
from ..models import Order
from ..signals import register_data_exporters


class MailExporter(BaseExporter):
    identifier = 'mailaddrs'
    verbose_name = _('Email addresses (text file)')

    def render(self, form_data: dict):
        qs = self.event.orders.filter(status__in=form_data['status'])
        addrs = qs.values('email')
        data = "\r\n".join(set(a['email'] for a in addrs))
        return 'pretixemails.txt', 'text/plain', data.encode("utf-8")

    @property
    def export_form_fields(self):
        return OrderedDict(
            [
                ('status',
                 forms.MultipleChoiceField(
                     label=_('Filter by status'),
                     initial=[Order.STATUS_PENDING, Order.STATUS_PAID],
                     choices=Order.STATUS_CHOICE,
                     widget=forms.CheckboxSelectMultiple,
                     required=False
                 )),
            ]
        )


@receiver(register_data_exporters, dispatch_uid="exporter_mail")
def register_mail_export(sender, **kwargs):
    return MailExporter
