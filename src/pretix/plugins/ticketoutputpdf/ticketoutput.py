import copy
import logging
import re
import uuid
from collections import OrderedDict
from io import BytesIO

import bleach
from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.files.storage import default_storage
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.formats import date_format
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

from pretix.base.i18n import language
from pretix.base.models import Order, OrderPosition
from pretix.base.templatetags.money import money_filter
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.plugins.ticketoutputpdf.signals import (
    get_fonts, layout_text_variables,
)

logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


DEFAULT_VARIABLES = OrderedDict((
    ("secret", {
        "label": _("Ticket code (barcode content)"),
        "editor_sample": "tdmruoekvkpbv1o2mv8xccvqcikvr58u",
        "evaluate": lambda orderposition, order, event: orderposition.secret
    }),
    ("order", {
        "label": _("Order code"),
        "editor_sample": "A1B2C",
        "evaluate": lambda orderposition, order, event: orderposition.order.code
    }),
    ("item", {
        "label": _("Product name"),
        "editor_sample": _("Sample product"),
        "evaluate": lambda orderposition, order, event: str(orderposition.item)
    }),
    ("variation", {
        "label": _("Variation name"),
        "editor_sample": _("Sample variation"),
        "evaluate": lambda op, order, event: str(op.variation) if op.variation else ''
    }),
    ("item_description", {
        "label": _("Product description"),
        "editor_sample": _("Sample product – sample variation"),
        "evaluate": lambda orderposition, order, event: (
            '{} - {}'.format(orderposition.item, orderposition.variation)
            if orderposition.variation else str(orderposition.item)
        )
    }),
    ("itemvar", {
        "label": _("Product name and variation"),
        "editor_sample": _("Sample product description"),
        "evaluate": lambda orderposition, order, event: str(orderposition.item.description)
    }),
    ("item_category", {
        "label": _("Product category"),
        "editor_sample": _("Ticket category"),
        "evaluate": lambda orderposition, order, event: (
            str(orderposition.item.category.name) if orderposition.item.category else ""
        )
    }),
    ("price", {
        "label": _("Price"),
        "editor_sample": _("123.45 EUR"),
        "evaluate": lambda op, order, event: money_filter(op.price, event.currency)
    }),
    ("attendee_name", {
        "label": _("Attendee name"),
        "editor_sample": _("John Doe"),
        "evaluate": lambda op, order, ev: op.attendee_name or (op.addon_to.attendee_name if op.addon_to else '')
    }),
    ("event_name", {
        "label": _("Event name"),
        "editor_sample": _("Sample event name"),
        "evaluate": lambda op, order, ev: str(ev.name)
    }),
    ("event_date", {
        "label": _("Event date"),
        "editor_sample": _("May 31st, 2017"),
        "evaluate": lambda op, order, ev: ev.get_date_from_display(show_times=False)
    }),
    ("event_date_range", {
        "label": _("Event date range"),
        "editor_sample": _("May 31st – June 4th, 2017"),
        "evaluate": lambda op, order, ev: ev.get_date_range_display()
    }),
    ("event_begin", {
        "label": _("Event begin date and time"),
        "editor_sample": _("2017-05-31 20:00"),
        "evaluate": lambda op, order, ev: ev.get_date_from_display(show_times=True)
    }),
    ("event_begin_time", {
        "label": _("Event begin time"),
        "editor_sample": _("20:00"),
        "evaluate": lambda op, order, ev: ev.get_time_from_display()
    }),
    ("event_admission", {
        "label": _("Event admission date and time"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_admission.astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATETIME_FORMAT"
        ) if ev.date_admission else ""
    }),
    ("event_admission_time", {
        "label": _("Event admission time"),
        "editor_sample": _("19:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_admission.astimezone(timezone(ev.settings.timezone)),
            "TIME_FORMAT"
        ) if ev.date_admission else ""
    }),
    ("event_location", {
        "label": _("Event location"),
        "editor_sample": _("Random City"),
        "evaluate": lambda op, order, ev: str(ev.location).replace("\n", "<br/>\n")
    }),
    ("invoice_name", {
        "label": _("Invoice address: name"),
        "editor_sample": _("John Doe"),
        "evaluate": lambda op, order, ev: order.invoice_address.name if getattr(order, 'invoice_address') else ''
    }),
    ("invoice_company", {
        "label": _("Invoice address: company"),
        "editor_sample": _("Sample company"),
        "evaluate": lambda op, order, ev: order.invoice_address.company if getattr(order, 'invoice_address') else ''
    }),
    ("addons", {
        "label": _("List of Add-Ons"),
        "editor_sample": _("Addon 1\nAddon 2"),
        "evaluate": lambda op, order, ev: "<br/>".join([
            '{} - {}'.format(p.item, p.variation) if p.variation else str(p.item)
            for p in op.addons.select_related('item', 'variation')
        ])
    }),
    ("organizer", {
        "label": _("Organizer name"),
        "editor_sample": _("Event organizer company"),
        "evaluate": lambda op, order, ev: str(order.event.organizer.name)
    }),
    ("organizer_info_text", {
        "label": _("Organizer info text"),
        "editor_sample": _("Event organizer info text"),
        "evaluate": lambda op, order, ev: str(order.event.settings.organizer_info_text)
    }),
))


def get_variables(event):
    v = copy.copy(DEFAULT_VARIABLES)
    for recv, res in layout_text_variables.send(sender=event):
        v.update(res)
    return v


class PdfTicketOutput(BaseTicketOutput):
    identifier = 'pdf'
    verbose_name = _('PDF output')
    download_button_text = _('PDF')

    def __init__(self, event, override_layout=None, override_background=None):
        self.override_layout = override_layout
        self.override_background = override_background
        self.variables = get_variables(event)
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
        if not o['content']:
            return '(error)'
        if o['content'] == 'other':
            return o['text'].replace("\n", "<br/>\n")
        elif o['content'].startswith('meta:'):
            return ev.meta_data.get(o['content'][5:]) or ''
        elif o['content'] in self.variables:
            try:
                return self.variables[o['content']]['evaluate'](op, order, ev)
            except:
                logger.exception('Failed to process variable.')
                return '(error)'
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
        text = re.sub(
            "<br[^>]*>", "<br/>",
            bleach.clean(
                self._get_text_content(op, order, o) or "",
                tags=["br"], attributes={}, styles=[], strip=True
            )
        )
        p = Paragraph(text, style=style)
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
        with language(order.locale):
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
        with language(order.locale):
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

    def _get_default_background(self):
        return open(finders.find('pretixpresale/pdf/ticket_default_a4.pdf'), "rb")

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
            bgf = self._get_default_background()
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
        layout = []

        event_s = self.settings.get('event_s', default=22, as_type=float)
        if event_s:
            layout.append({
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
            layout.append({
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
            layout.append({
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
            layout.append({
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
            layout.append({
                'type': 'barcodearea',
                'left': self.settings.get('qr_x', default=10, as_type=float),
                'bottom': self.settings.get('qr_y', default=120, as_type=float),
                'size': qr_s,
            })

        code_s = self.settings.get('code_s', default=11, as_type=float)
        if code_s:
            layout.append({
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
            layout.append({
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

        return layout
