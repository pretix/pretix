from io import BytesIO

from django.core.files.base import ContentFile
from django.utils.translation import ugettext as _
from PyPDF2.merger import PdfFileMerger

from pretix.base.exporter import BaseExporter
from pretix.base.i18n import language
from pretix.base.models import Order, OrderPosition

from .ticketoutput import PdfTicketOutput


class AllTicketsPDF(BaseExporter):
    name = "alltickets"
    verbose_name = _("All paid PDF tickets in one file")
    identifier = "pdfoutput_all_tickets"

    def render(self, form_data):
        merger = PdfFileMerger()

        o = PdfTicketOutput(self.event)
        qs = OrderPosition.objects.filter(order__event=self.event, order__status=Order.STATUS_PAID).select_related(
            'order', 'item', 'variation'
        )

        for op in qs:
            if op.addon_to_id and not self.event.settings.ticket_download_addons:
                continue
            if not op.item.admission and not self.event.settings.ticket_download_nonadm:
                continue

            with language(op.order.locale):
                buffer = BytesIO()
                p = o._create_canvas(buffer)
                layout = o.layout_map.get(op.item_id, o.default_layout)
                o._draw_page(layout, p, op, op.order)
                p.save()
                outbuffer = o._render_with_background(layout, buffer)
                merger.append(ContentFile(outbuffer.read()))

        outbuffer = BytesIO()
        merger.write(outbuffer)
        merger.close()
        outbuffer.seek(0)
        return '{}_tickets.pdf'.format(self.event.slug), 'application/pdf', outbuffer.read()
