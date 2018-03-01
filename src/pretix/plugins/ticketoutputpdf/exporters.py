from io import BytesIO

from django.utils.translation import ugettext as _

from pretix.base.exporter import BaseExporter
from pretix.base.models import Order, OrderPosition

from .ticketoutput import PdfTicketOutput


class AllTicketsPDF(BaseExporter):
    name = "alltickets"
    verbose_name = _("All paid PDF tickets in one file")
    identifier = "pdfoutput_all_tickets"

    def render(self, form_data):
        o = PdfTicketOutput(self.event)
        qs = OrderPosition.objects.filter(order__event=self.event, order__status=Order.STATUS_PAID).select_related(
            'order', 'item', 'variation'
        )
        buffer = BytesIO()
        p = o._create_canvas(buffer)
        for op in qs:
            if op.addon_to_id and not self.event.settings.ticket_download_addons:
                continue
            if not op.item.admission and not self.event.settings.ticket_download_nonadm:
                continue
            o._draw_page(p, op, op.order)

        p.save()
        outbuffer = o._render_with_background(buffer)
        return '{}_tickets.pdf'.format(self.event.slug), 'application/pdf', outbuffer.read()
