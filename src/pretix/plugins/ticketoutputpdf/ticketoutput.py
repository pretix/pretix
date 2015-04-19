from io import BytesIO
import logging
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from pretix.base.models import Order

from pretix.base.ticketoutput import BaseTicketOutput


logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


class PdfTicketOutput(BaseTicketOutput):

    identifier = 'pdf'
    verbose_name = _('PDF output')
    download_button_text = _('Download PDF')
    download_button_icon = 'fa-print'

    def generate(self, request, order):
        from reportlab.graphics.shapes import Drawing
        from reportlab.pdfgen import canvas
        from reportlab.lib import pagesizes, units
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics import renderPDF
        from PyPDF2 import PdfFileWriter, PdfFileReader

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="order%s%s.pdf"' % (request.event.slug, order.code)

        pagesize = request.event.settings.get('ticketpdf_pagesize', default='A4')
        if hasattr(pagesizes, pagesize):
            pagesize = getattr(pagesizes, pagesize)
        else:
            pagesize = pagesizes.A4
        defaultfname = finders.find('pretixpresale/pdf/ticket_default_a4.pdf')
        fname = request.event.settings.get('ticketpdf_background', default=defaultfname)
        # TODO: Handle file objects

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=pagesize)

        for op in order.positions.all().select_related('item', 'variation'):
            p.setFont("Helvetica", 22)
            p.drawString(15 * units.mm, 235 * units.mm, str(request.event.name))

            p.setFont("Helvetica", 17)
            item = str(op.item.name)
            if op.variation:
                item += " – " + str(op.variation)
            p.drawString(15 * units.mm, 220 * units.mm, item)

            p.setFont("Helvetica", 17)
            p.drawString(15 * units.mm, 210 * units.mm, "%s %s" % (str(op.price), request.event.currency))

            reqs = 80 * units.mm
            qrw = QrCodeWidget(op.identity, barLevel='H')
            b = qrw.getBounds()
            w = b[2] - b[0]
            h = b[3] - b[1]
            d = Drawing(reqs, reqs, transform=[reqs / w, 0, 0, reqs / h, 0, 0])
            d.add(qrw)
            renderPDF.draw(d, p, 10 * units.mm, 130 * units.mm)

            p.setFont("Helvetica", 11)
            p.drawString(15 * units.mm, 130 * units.mm, op.identity)

            p.showPage()

        p.save()

        buffer.seek(0)
        new_pdf = PdfFileReader(buffer)
        output = PdfFileWriter()
        for page in new_pdf.pages:
            bg_pdf = PdfFileReader(open(fname, "rb"))
            bg_page = bg_pdf.getPage(0)
            bg_page.mergePage(page)
            output.addPage(bg_page)

        output.write(response)
        return response
