from collections import OrderedDict
from io import BytesIO

from django import forms
from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _, gettext_lazy
from jsonfallback.functions import JSONExtract
from PyPDF2.merger import PdfFileMerger

from pretix.base.exporter import BaseExporter
from pretix.base.i18n import language
from pretix.base.models import Event, Order, OrderPosition
from pretix.base.settings import PERSON_NAME_SCHEMES

from .ticketoutput import PdfTicketOutput


class AllTicketsPDF(BaseExporter):
    name = "alltickets"
    verbose_name = gettext_lazy("All PDF tickets in one file")
    identifier = "pdfoutput_all_tickets"

    @property
    def export_form_fields(self):
        name_scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme] if not self.is_multievent else None
        d = OrderedDict(
            [
                ('include_pending',
                 forms.BooleanField(
                     label=_('Include pending orders'),
                     required=False
                 )),
                ('order_by',
                 forms.ChoiceField(
                     label=_('Sort by'),
                     choices=[
                         ('name', _('Attendee name')),
                         ('code', _('Order code')),
                     ] + ([
                         ('name:{}'.format(k), _('Attendee name: {part}').format(part=label))
                         for k, label, w in name_scheme['fields']
                     ] if settings.JSON_FIELD_AVAILABLE and name_scheme and len(name_scheme['fields']) > 1 else []),
                 )),
            ]
        )
        return d

    def render(self, form_data):
        merger = PdfFileMerger()
        qs = OrderPosition.objects.filter(
            order__event__in=self.events
        ).prefetch_related(
            'answers', 'answers__question'
        ).select_related('order', 'item', 'variation', 'addon_to')

        if form_data.get('include_pending'):
            qs = qs.filter(order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING])
        else:
            qs = qs.filter(order__status__in=[Order.STATUS_PAID])

        if form_data.get('order_by') == 'name':
            qs = qs.order_by('attendee_name_cached', 'order__code')
        elif form_data.get('order_by') == 'code':
            qs = qs.order_by('order__code')
        elif form_data.get('order_by', '').startswith('name:'):
            part = form_data['order_by'][5:]
            qs = qs.annotate(
                resolved_name=Coalesce('attendee_name_parts', 'addon_to__attendee_name_parts', 'order__invoice_address__name_parts')
            ).annotate(
                resolved_name_part=JSONExtract('resolved_name', part)
            ).order_by(
                'resolved_name_part'
            )

        o = PdfTicketOutput(Event.objects.none())
        for op in qs:
            if not op.generate_ticket:
                continue

            if op.order.event != o.event:
                o = PdfTicketOutput(op.event)

            with language(op.order.locale):
                layout = o.layout_map.get(
                    (op.item_id, op.order.sales_channel),
                    o.layout_map.get(
                        (op.item_id, 'web'),
                        o.default_layout
                    )
                )
                outbuffer = o._draw_page(layout, op, op.order)
                merger.append(ContentFile(outbuffer.read()))

        outbuffer = BytesIO()
        merger.write(outbuffer)
        merger.close()
        outbuffer.seek(0)

        if self.is_multievent:
            return '{}_tickets.pdf'.format(self.events.first().organizer.slug), 'application/pdf', outbuffer.read()
        else:
            return '{}_tickets.pdf'.format(self.event.slug), 'application/pdf', outbuffer.read()
