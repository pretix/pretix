import copy
import logging
from collections import OrderedDict
from io import BytesIO

from django import forms
from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.files.storage import default_storage
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Order
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.control.forms import ExtFileField

logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


class PdfTicketOutput(BaseTicketOutput):
    identifier = 'pdf'
    verbose_name = _('PDF output')
    download_button_text = _('PDF')

    def _draw_page(self, p, op, order):
        from reportlab.graphics.shapes import Drawing
        from reportlab.lib import units
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics import renderPDF

        event_s = self.settings.get('event_s', default=22, as_type=float)
        if event_s:
            p.setFont("Helvetica", event_s)
            event_x = self.settings.get('event_x', default=15, as_type=float)
            event_y = self.settings.get('event_y', default=235, as_type=float)
            p.drawString(event_x * units.mm, event_y * units.mm, str(self.event.name))

        order_s = self.settings.get('order_s', default=17, as_type=float)
        if order_s:
            p.setFont("Helvetica", order_s)
            order_x = self.settings.get('order_x', default=15, as_type=float)
            order_y = self.settings.get('order_y', default=220, as_type=float)
            p.drawString(order_x * units.mm, order_y * units.mm, _('Order code: {code}').format(code=order.code))

        name_s = self.settings.get('name_s', default=17, as_type=float)
        if name_s:
            p.setFont("Helvetica", name_s)
            name_x = self.settings.get('name_x', default=15, as_type=float)
            name_y = self.settings.get('name_y', default=210, as_type=float)
            item = str(op.item.name)
            if op.variation:
                item += " – " + str(op.variation)
            p.drawString(name_x * units.mm, name_y * units.mm, item)

        price_s = self.settings.get('price_s', default=17, as_type=float)
        if price_s:
            p.setFont("Helvetica", price_s)
            price_x = self.settings.get('price_x', default=15, as_type=float)
            price_y = self.settings.get('price_y', default=200, as_type=float)
            p.drawString(price_x * units.mm, price_y * units.mm, "%s %s" % (str(op.price), self.event.currency))

        qr_s = self.settings.get('qr_s', default=80, as_type=float)
        if qr_s:
            reqs = qr_s * units.mm
            qrw = QrCodeWidget(op.secret, barLevel='H')
            b = qrw.getBounds()
            w = b[2] - b[0]
            h = b[3] - b[1]
            d = Drawing(reqs, reqs, transform=[reqs / w, 0, 0, reqs / h, 0, 0])
            d.add(qrw)
            qr_x = self.settings.get('qr_x', default=10, as_type=float)
            qr_y = self.settings.get('qr_y', default=120, as_type=float)
            renderPDF.draw(d, p, qr_x * units.mm, qr_y * units.mm)

        code_s = self.settings.get('code_s', default=11, as_type=float)
        if code_s:
            p.setFont("Helvetica", code_s)
            code_x = self.settings.get('code_x', default=15, as_type=float)
            code_y = self.settings.get('code_y', default=120, as_type=float)
            p.drawString(code_x * units.mm, code_y * units.mm, op.secret)

        attendee_s = self.settings.get('attendee_s', default=0, as_type=float)
        if code_s and op.attendee_name:
            p.setFont("Helvetica", attendee_s)
            attendee_x = self.settings.get('attendee_x', default=15, as_type=float)
            attendee_y = self.settings.get('attendee_y', default=90, as_type=float)
            p.drawString(attendee_x * units.mm, attendee_y * units.mm, op.attendee_name)

        p.showPage()

    def generate_order(self, order: Order):
        buffer = BytesIO()
        p = self._create_canvas(buffer)
        for op in order.positions.all():
            self._draw_page(p, op, order)
        p.save()
        outbuffer = self._render_with_background(buffer)
        return 'order%s%s.pdf' % (self.event.slug, order.code), 'application/pdf', outbuffer.read()

    def generate(self, op):
        buffer = BytesIO()
        p = self._create_canvas(buffer)
        order = op.order
        self._draw_page(p, op, order)
        p.save()
        outbuffer = self._render_with_background(buffer)
        return 'order%s%s.pdf' % (self.event.slug, order.code), 'application/pdf', outbuffer.read()

    def _create_canvas(self, buffer):
        from reportlab.pdfgen import canvas
        from reportlab.lib import pagesizes

        pagesize = self.settings.get('pagesize', default='A4')
        if hasattr(pagesizes, pagesize):
            pagesize = getattr(pagesizes, pagesize)
        else:
            pagesize = pagesizes.A4
        orientation = self.settings.get('orientation', default='portrait')
        if hasattr(pagesizes, orientation):
            pagesize = getattr(pagesizes, orientation)(pagesize)

        return canvas.Canvas(buffer, pagesize=pagesize)

    def _render_with_background(self, buffer):
        from PyPDF2 import PdfFileWriter, PdfFileReader
        buffer.seek(0)
        new_pdf = PdfFileReader(buffer)
        output = PdfFileWriter()
        bg_file = self.settings.get('background', as_type=File)
        if isinstance(bg_file, File):
            bgf = default_storage.open(bg_file.name, "rb")
        else:
            bgf = open(finders.find('pretixpresale/pdf/ticket_default_a4.pdf'), "rb")
        bg_pdf = PdfFileReader(bgf)
        for page in new_pdf.pages:
            bg_page = copy.copy(bg_pdf.getPage(0))
            bg_page.mergePage(page)
            output.addPage(bg_page)

        outbuffer = BytesIO()
        output.write(outbuffer)
        outbuffer.seek(0)
        return outbuffer

    @property
    def settings_form_fields(self) -> dict:
        return OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('paper_size',
                 forms.ChoiceField(
                     label=_('Paper size'),
                     choices=(
                         ('A4', 'A4'),
                         ('A5', 'A5'),
                         ('B4', 'B4'),
                         ('B5', 'B5'),
                         ('letter', 'Letter'),
                         ('legal', 'Legal'),
                     ),
                     required=False
                 )),
                ('orientation',
                 forms.ChoiceField(
                     label=_('Paper orientation'),
                     choices=(
                         ('portrait', _('Portrait')),
                         ('landscape', _('Landscape')),
                     ),
                     required=False
                 )),
                ('background',
                 ExtFileField(
                     label=_('Background PDF'),
                     ext_whitelist=(".pdf", ),
                     required=False
                 )),
                ('qr_x', forms.FloatField(label=_('QR-Code x position (mm)'), required=False)),
                ('qr_y', forms.FloatField(label=_('QR-Code y position (mm)'), required=False)),
                ('qr_s', forms.FloatField(label=_('QR-Code size (mm)'), required=False)),
                ('code_x', forms.FloatField(label=_('Ticket code x position (mm)'), required=False)),
                ('code_y', forms.FloatField(label=_('Ticket code y position (mm)'), required=False)),
                ('code_s', forms.FloatField(label=_('Ticket code size (mm)'), required=False,
                                            help_text=_('Visible by default, set this to 0 to hide the element.'))),
                ('order_x', forms.FloatField(label=_('Order x position (mm)'), required=False)),
                ('order_y', forms.FloatField(label=_('Order y position (mm)'), required=False)),
                ('order_s', forms.FloatField(label=_('Order size (mm)'), required=False,
                                             help_text=_('Visible by default, set this to 0 to hide the element.'))),
                ('name_x', forms.FloatField(label=_('Product name x position (mm)'), required=False)),
                ('name_y', forms.FloatField(label=_('Product name y position (mm)'), required=False)),
                ('name_s', forms.FloatField(label=_('Product name size (mm)'), required=False,
                                            help_text=_('Visible by default, set this to 0 to hide the element.'))),
                ('price_x', forms.FloatField(label=_('Price x position (mm)'), required=False)),
                ('price_y', forms.FloatField(label=_('Price y position (mm)'), required=False)),
                ('price_s', forms.FloatField(label=_('Price size (mm)'), required=False,
                                             help_text=_('Visible by default, set this to 0 to hide the element.'))),
                ('event_x', forms.FloatField(label=_('Event name x position (mm)'), required=False)),
                ('event_y', forms.FloatField(label=_('Event name y position (mm)'), required=False)),
                ('event_s', forms.FloatField(label=_('Event name size (mm)'), required=False,
                                             help_text=_('Visible by default, set this to 0 to hide the element.'))),
                ('attendee_x', forms.FloatField(label=_('Attendee name x position (mm)'), required=False)),
                ('attendee_y', forms.FloatField(label=_('Attendee name y position (mm)'), required=False)),
                ('attendee_s', forms.FloatField(label=_('Attendee name size (mm)'), required=False,
                                                help_text=_('Invisible by default, set this to a number greater than 0 '
                                                            'to show.')))
            ]
        )
