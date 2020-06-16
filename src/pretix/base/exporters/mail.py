from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from pretix.base.models import OrderPosition

from ..exporter import BaseExporter
from ..models import Order
from ..signals import (
    register_data_exporters, register_multievent_data_exporters,
)


class MailExporter(BaseExporter):
    identifier = 'mailaddrs'
    verbose_name = _('Email addresses (text file)')

    def render(self, form_data: dict):
        qs = Order.objects.filter(event__in=self.events, status__in=form_data['status']).prefetch_related('event')
        addrs = qs.values('email')
        pos = OrderPosition.objects.filter(
            order__event__in=self.events, order__status__in=form_data['status']
        ).values('attendee_email')
        data = "\r\n".join(set(a['email'] for a in addrs if a['email'])
                           | set(a['attendee_email'] for a in pos if a['attendee_email']))

        if self.is_multievent:
            return '{}_pretixemails.txt'.format(self.events.first().organizer.slug), 'text/plain', data.encode("utf-8")
        else:
            return '{}_pretixemails.txt'.format(self.event.slug), 'text/plain', data.encode("utf-8")

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


@receiver(register_multievent_data_exporters, dispatch_uid="multiexporter_mail")
def register_multievent_mail_export(sender, **kwargs):
    return MailExporter
