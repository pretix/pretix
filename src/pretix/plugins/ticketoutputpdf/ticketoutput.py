import json
import logging
from io import BytesIO

from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from PyPDF2 import PdfFileMerger

from pretix.base.i18n import language
from pretix.base.models import Order, OrderPosition
from pretix.base.pdf import Renderer
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.plugins.ticketoutputpdf.models import (
    TicketLayout, TicketLayoutItem,
)
from pretix.plugins.ticketoutputpdf.signals import override_layout

logger = logging.getLogger('pretix.plugins.ticketoutputpdf')


class PdfTicketOutput(BaseTicketOutput):
    identifier = 'pdf'
    verbose_name = _('PDF output')
    download_button_text = _('PDF')
    multi_download_button_text = _('Download tickets (PDF)')
    long_download_button_text = _('Download ticket (PDF)')

    def __init__(self, event, override_layout=None, override_background=None):
        self.override_layout = override_layout
        self.override_background = override_background
        super().__init__(event)

    @cached_property
    def layout_map(self):
        if not hasattr(self.event, '_ticketoutputpdf_cache_layoutmap'):
            self.event._ticketoutputpdf_cache_layoutmap = {
                (bi.item_id, bi.sales_channel): bi.layout
                for bi in TicketLayoutItem.objects.select_related('layout').filter(item__event=self.event)
            }
        return self.event._ticketoutputpdf_cache_layoutmap

    @cached_property
    def default_layout(self):
        if not hasattr(self.event, '_ticketoutputpdf_cache_default_layout'):
            try:
                self.event._ticketoutputpdf_cache_default_layout = self.event.ticket_layouts.get(default=True)
            except TicketLayout.DoesNotExist:
                self.event._ticketoutputpdf_cache_default_layout = TicketLayout(
                    layout=json.dumps(self._default_layout())
                )
        return self.event._ticketoutputpdf_cache_default_layout

    def _register_fonts(self):
        Renderer._register_fonts()

    def _draw_page(self, layout: TicketLayout, op: OrderPosition, order: Order):
        buffer = BytesIO()
        objs = self.override_layout or json.loads(layout.layout) or self._legacy_layout()
        bg_file = layout.background

        if self.override_background:
            bgf = default_storage.open(self.override_background.name, "rb")
        elif isinstance(bg_file, File) and bg_file.name:
            bgf = default_storage.open(bg_file.name, "rb")
        else:
            bgf = self._get_default_background()

        p = self._create_canvas(buffer)
        renderer = Renderer(self.event, objs, bgf)
        renderer.draw_page(p, order, op)
        p.save()
        return renderer.render_background(buffer, _('Ticket'))

    def generate_order(self, order: Order):
        merger = PdfFileMerger()
        with language(order.locale, self.event.settings.region):
            for op in order.positions_with_tickets:
                layout = override_layout.send_chained(
                    order.event, 'layout', orderposition=op, layout=self.layout_map.get(
                        (op.item_id, order.sales_channel),
                        self.layout_map.get(
                            (op.item_id, 'web'),
                            self.default_layout
                        )
                    )
                )
                outbuffer = self._draw_page(layout, op, order)
                merger.append(ContentFile(outbuffer.read()))

        outbuffer = BytesIO()
        merger.write(outbuffer)
        merger.close()
        outbuffer.seek(0)
        return 'order%s%s.pdf' % (self.event.slug, order.code), 'application/pdf', outbuffer.read()

    def generate(self, op):
        order = op.order

        layout = override_layout.send_chained(
            order.event, 'layout', orderposition=op, layout=self.layout_map.get(
                (op.item_id, order.sales_channel),
                self.layout_map.get(
                    (op.item_id, 'web'),
                    self.default_layout
                )
            )
        )
        with language(order.locale, self.event.settings.region):
            outbuffer = self._draw_page(layout, op, order)
        return 'order%s%s.pdf' % (self.event.slug, order.code), 'application/pdf', outbuffer.read()

    def _create_canvas(self, buffer):
        from reportlab.lib import pagesizes
        from reportlab.pdfgen import canvas

        # Doesn't matter as we'll overpaint it over a background later
        pagesize = pagesizes.A4

        self._register_fonts()
        return canvas.Canvas(buffer, pagesize=pagesize)

    def _get_default_background(self):
        return open(finders.find('pretixpresale/pdf/ticket_default_a4.pdf'), "rb")

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
             "content": "event_begin", "text": "2017-05-31 20:00", "align": "left"},
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
            {"type": "barcodearea", "left": "130.40", "bottom": "204.50", "size": "64.00"},
            {"type": "poweredby", "left": "88.72", "bottom": "10.00", "size": "20.00"},
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
