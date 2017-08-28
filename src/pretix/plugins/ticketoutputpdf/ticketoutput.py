import copy
import logging
import uuid
from io import BytesIO

from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.files.storage import default_storage
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.formats import date_format, localize
from django.utils.translation import ugettext_lazy as _
from pytz import timezone
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import Color
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import getAscentDescent
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from pretix.base.models import Order, OrderPosition
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.plugins.ticketoutputpdf.signals import get_fonts

logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


class PdfTicketOutput(BaseTicketOutput):
    identifier = 'pdf'
    verbose_name = _('PDF output')
    download_button_text = _('PDF')

    def __init__(self, event, override_layout=None, override_background=None):
        self.override_layout = override_layout
        self.override_background = override_background
        super().__init__(event)

    def _register_fonts(self):
        pdfmetrics.registerFont(TTFont('Open Sans', finders.find('fonts/OpenSans-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('Open Sans I', finders.find('fonts/OpenSans-Italic.ttf')))
        pdfmetrics.registerFont(TTFont('Open Sans B', finders.find('fonts/OpenSans-Bold.ttf')))
        pdfmetrics.registerFont(TTFont('Open Sans B I', finders.find('fonts/OpenSans-BoldItalic.ttf')))

        for family, styles in get_fonts().items():
            pdfmetrics.registerFont(TTFont(family, finders.find(styles['regular']['truetype'])))
            if 'italic' in styles:
                pdfmetrics.registerFont(TTFont(family + ' I', finders.find(styles['italic']['truetype'])))
            if 'bold' in styles:
                pdfmetrics.registerFont(TTFont(family + ' B', finders.find(styles['bold']['truetype'])))
            if 'bolditalic' in styles:
                pdfmetrics.registerFont(TTFont(family + ' B I', finders.find(styles['bolditalic']['truetype'])))

    def _draw_barcodearea(self, canvas: Canvas, op: OrderPosition, o: dict):
        reqs = float(o['size']) * mm
        qrw = QrCodeWidget(op.secret, barLevel='H', barHeight=reqs, barWidth=reqs)
        d = Drawing(reqs, reqs)
        d.add(qrw)
        qr_x = float(o['left']) * mm
        qr_y = float(o['bottom']) * mm
        renderPDF.draw(d, canvas, qr_x, qr_y)

    def _get_text_content(self, op: OrderPosition, order: Order, o: dict):
        ev = op.subevent or order.event
        if o['content'] == 'other':
            return o['text'].replace("\n", "<br/>\n")
        elif o['content'].startswith('meta:'):
            return ev.meta_data.get(o['content'][5:])
        elif o['content'] == 'order':
            return order.code
        elif o['content'] == 'item':
            return str(op.item)
        elif o['content'] == 'item_description':
            return str(op.item.description)
        elif o['content'] == 'organizer':
            return str(order.event.organizer.name)
        elif o['content'] == 'organizer_info_text':
            return str(order.event.settings.organizer_info_text)
        elif o['content'] == 'secret':
            return op.secret
        elif o['content'] == 'variation':
            return str(op.variation) if op.variation else ''
        elif o['content'] == 'itemvar':
            return '{} - {}'.format(op.item, op.variation) if op.variation else str(op.item)
        elif o['content'] == 'price':
            return '{} {}'.format(order.event.currency, localize(op.price))
        elif o['content'] == 'attendee_name':
            return op.attendee_name or (op.addon_to.attendee_name if op.addon_to else '')
        elif o['content'] == 'event_name':
            return str(ev.name)
        elif o['content'] == 'event_location':
            return str(ev.location).replace("\n", "<br/>\n")
        elif o['content'] == 'event_date':
            return ev.get_date_from_display(show_times=False)
        elif o['content'] == 'event_date_range':
            return ev.get_date_range_display()
        elif o['content'] == 'event_begin':
            return ev.get_date_from_display(show_times=True)
        elif o['content'] == 'event_begin_time':
            return ev.get_time_from_display()
        elif o['content'] == 'event_admission':
            if ev.date_admission:
                tz = timezone(order.event.settings.timezone)
                return date_format(ev.date_admission.astimezone(tz), "SHORT_DATETIME_FORMAT")
        elif o['content'] == 'event_admission_time':
            if ev.date_admission:
                tz = timezone(order.event.settings.timezone)
                return date_format(ev.date_admission.astimezone(tz), "TIME_FORMAT")
        elif o['content'] == 'invoice_name':
            try:
                return order.invoice_address.name
            except:
                return ""
        elif o['content'] == 'invoice_company':
            try:
                return order.invoice_address.company
            except:
                return ""
        elif o['content'] == 'addons':
            return "<br/>".join([
                '{} - {}'.format(p.item, p.variation) if p.variation else str(p.item)
                for p in op.addons.select_related('item', 'variation')
            ])
        return ''

    def _draw_textarea(self, canvas: Canvas, op: OrderPosition, order: Order, o: dict):
        font = o['fontfamily']
        if o['bold']:
            font += ' B'
        if o['italic']:
            font += ' I'

        align_map = {
            'left': TA_LEFT,
            'center': TA_CENTER,
            'right': TA_RIGHT
        }
        style = ParagraphStyle(
            name=uuid.uuid4().hex,
            fontName=font,
            fontSize=float(o['fontsize']),
            leading=float(o['fontsize']),
            autoLeading="max",
            textColor=Color(o['color'][0] / 255, o['color'][1] / 255, o['color'][2] / 255),
            alignment=align_map[o['align']]
        )

        p = Paragraph(self._get_text_content(op, order, o), style=style)
        p.wrapOn(canvas, float(o['width']) * mm, 1000 * mm)
        # p_size = p.wrap(float(o['width']) * mm, 1000 * mm)
        ad = getAscentDescent(font, float(o['fontsize']))
        p.drawOn(canvas, float(o['left']) * mm, float(o['bottom']) * mm - ad[1])

    def _draw_page(self, canvas: Canvas, op: OrderPosition, order: Order):
        objs = self.override_layout or self.settings.get('layout', as_type=list) or self._legacy_layout()
        for o in objs:
            if o['type'] == "barcodearea":
                self._draw_barcodearea(canvas, op, o)
            elif o['type'] == "textarea":
                self._draw_textarea(canvas, op, order, o)

        canvas.showPage()

    def generate_order(self, order: Order):
        buffer = BytesIO()
        p = self._create_canvas(buffer)
        for op in order.positions.all():
            if op.addon_to_id and not self.event.settings.ticket_download_addons:
                continue
            if not op.item.admission and not self.event.settings.ticket_download_nonadm:
                continue
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

        # Doesn't matter as we'll overpaint it over a background later
        pagesize = pagesizes.A4

        self._register_fonts()
        return canvas.Canvas(buffer, pagesize=pagesize)

    def _render_with_background(self, buffer, title=_('Ticket')):
        from PyPDF2 import PdfFileWriter, PdfFileReader
        buffer.seek(0)
        new_pdf = PdfFileReader(buffer)
        output = PdfFileWriter()
        bg_file = self.settings.get('background', as_type=File)
        if self.override_background:
            bgf = default_storage.open(self.override_background.name, "rb")
        elif isinstance(bg_file, File):
            bgf = default_storage.open(bg_file.name, "rb")
        else:
            bgf = open(finders.find('pretixpresale/pdf/ticket_default_a4.pdf'), "rb")
        bg_pdf = PdfFileReader(bgf)

        for page in new_pdf.pages:
            bg_page = copy.copy(bg_pdf.getPage(0))
            bg_page.mergePage(page)
            output.addPage(bg_page)

        output.addMetadata({
            '/Title': str(title),
            '/Creator': 'pretix',
        })
        outbuffer = BytesIO()
        output.write(outbuffer)
        outbuffer.seek(0)
        return outbuffer

    def settings_content_render(self, request: HttpRequest) -> str:
        """
        When the event's administrator visits the event configuration
        page, this method is called. It may return HTML containing additional information
        that is displayed below the form fields configured in ``settings_form_fields``.
        """
        template = get_template('pretixplugins/ticketoutputpdf/form.html')
        return template.render({
            'request': request
        })

    def _legacy_layout(self):
        if self.settings.get('background'):
            return self._migrate_from_old_settings()
        else:
            return self._default_layout()

    def _default_layout(self):
        return [
            {"type": "textarea", "left": "17.50", "bottom": "274.60", "fontsize": "16.0", "color": [0, 0, 0, 1],
             "fontfamily": "Open Sans", "bold": False, "italic": False, "width": "175.00", "content": "event_name",
             "text": "Sample event name", "align": "left"},
            {"type": "textarea", "left": "17.50", "bottom": "262.90", "fontsize": "13.0", "color": [0, 0, 0, 1],
             "fontfamily": "Open Sans", "bold": False, "italic": False, "width": "110.00", "content": "itemvar",
             "text": "Sample product – sample variation", "align": "left"},
            {"type": "textarea", "left": "17.50", "bottom": "252.50", "fontsize": "13.0", "color": [0, 0, 0, 1],
             "fontfamily": "Open Sans", "bold": False, "italic": False, "width": "110.00", "content": "attendee_name",
             "text": "John Doe", "align": "left"},
            {"type": "textarea", "left": "17.50", "bottom": "242.10", "fontsize": "13.0", "color": [0, 0, 0, 1],
             "fontfamily": "Open Sans", "bold": False, "italic": False, "width": "110.00",
             "content": "event_date_range", "text": "May 31st, 2017", "align": "left"},
            {"type": "textarea", "left": "17.50", "bottom": "204.80", "fontsize": "13.0", "color": [0, 0, 0, 1],
             "fontfamily": "Open Sans", "bold": False, "italic": False, "width": "110.00", "content": "event_location",
             "text": "Random City", "align": "left"},
            {"type": "textarea", "left": "17.50", "bottom": "194.50", "fontsize": "13.0", "color": [0, 0, 0, 1],
             "fontfamily": "Open Sans", "bold": False, "italic": False, "width": "30.00", "content": "order",
             "text": "A1B2C", "align": "left"},
            {"type": "textarea", "left": "52.50", "bottom": "194.50", "fontsize": "13.0", "color": [0, 0, 0, 1],
             "fontfamily": "Open Sans", "bold": False, "italic": False, "width": "45.00", "content": "price",
             "text": "123.45 EUR", "align": "right"},
            {"type": "textarea", "left": "102.50", "bottom": "194.50", "fontsize": "13.0", "color": [0, 0, 0, 1],
             "fontfamily": "Open Sans", "bold": False, "italic": False, "width": "90.00", "content": "secret",
             "text": "tdmruoekvkpbv1o2mv8xccvqcikvr58u", "align": "left"},
            {"type": "barcodearea", "left": "130.40", "bottom": "204.50", "size": "64.00"}
        ]

    def _migrate_from_old_settings(self):
        l = []

        event_s = self.settings.get('event_s', default=22, as_type=float)
        if event_s:
            l.append({
                'type': 'textarea',
                'fontfamily': 'Helvetica',
                'left': self.settings.get('event_x', default=15, as_type=float),
                'bottom': self.settings.get('event_y', default=235, as_type=float),
                'fontsize': event_s,
                'color': [0, 0, 0, 1],
                'bold': False,
                'italic': False,
                'width': 150,
                'content': 'event_name',
                'text': 'Sample event',
                'align': 'left'
            })

        order_s = self.settings.get('order_s', default=17, as_type=float)
        if order_s:
            l.append({
                'type': 'textarea',
                'fontfamily': 'Helvetica',
                'left': self.settings.get('order_x', default=15, as_type=float),
                'bottom': self.settings.get('order_y', default=220, as_type=float),
                'fontsize': order_s,
                'color': [0, 0, 0, 1],
                'bold': False,
                'italic': False,
                'width': 150,
                'content': 'order',
                'text': 'AB1C2',
                'align': 'left'
            })

        name_s = self.settings.get('name_s', default=17, as_type=float)
        if name_s:
            l.append({
                'type': 'textarea',
                'fontfamily': 'Helvetica',
                'left': self.settings.get('name_x', default=15, as_type=float),
                'bottom': self.settings.get('name_y', default=210, as_type=float),
                'fontsize': name_s,
                'color': [0, 0, 0, 1],
                'bold': False,
                'italic': False,
                'width': 150,
                'content': 'itemvar',
                'text': 'Sample Producs - XS',
                'align': 'left'
            })

        price_s = self.settings.get('price_s', default=17, as_type=float)
        if price_s:
            l.append({
                'type': 'textarea',
                'fontfamily': 'Helvetica',
                'left': self.settings.get('price_x', default=15, as_type=float),
                'bottom': self.settings.get('price_y', default=200, as_type=float),
                'fontsize': price_s,
                'color': [0, 0, 0, 1],
                'bold': False,
                'italic': False,
                'width': 150,
                'content': 'price',
                'text': 'EUR 12,34',
                'align': 'left'
            })

        qr_s = self.settings.get('qr_s', default=80, as_type=float)
        if qr_s:
            l.append({
                'type': 'barcodearea',
                'left': self.settings.get('qr_x', default=10, as_type=float),
                'bottom': self.settings.get('qr_y', default=120, as_type=float),
                'size': qr_s,
            })

        code_s = self.settings.get('code_s', default=11, as_type=float)
        if code_s:
            l.append({
                'type': 'textarea',
                'fontfamily': 'Helvetica',
                'left': self.settings.get('code_x', default=15, as_type=float),
                'bottom': self.settings.get('code_y', default=120, as_type=float),
                'fontsize': code_s,
                'color': [0, 0, 0, 1],
                'bold': False,
                'italic': False,
                'width': 150,
                'content': 'secret',
                'text': 'asdsdgjfgbgkjdastjrxfdg',
                'align': 'left'
            })

        attendee_s = self.settings.get('attendee_s', default=0, as_type=float)
        if attendee_s:
            l.append({
                'type': 'textarea',
                'fontfamily': 'Helvetica',
                'left': self.settings.get('attendee_x', default=15, as_type=float),
                'bottom': self.settings.get('attendee_y', default=90, as_type=float),
                'fontsize': attendee_s,
                'color': [0, 0, 0, 1],
                'bold': False,
                'italic': False,
                'width': 150,
                'content': 'attendee_name',
                'text': 'John Doe',
                'align': 'left'
            })

        return l
