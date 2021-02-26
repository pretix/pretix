import copy
import hashlib
import itertools
import logging
import os
import subprocess
import tempfile
import uuid
from collections import OrderedDict
from functools import partial
from io import BytesIO

from arabic_reshaper import ArabicReshaper
from bidi.algorithm import get_display
from django.conf import settings
from django.contrib.staticfiles import finders
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.html import conditional_escape
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from PyPDF2 import PdfFileReader
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
from pretix.base.invoice import ThumbnailingImageReader
from pretix.base.models import Order, OrderPosition, Question
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.signals import layout_image_variables, layout_text_variables
from pretix.base.templatetags.money import money_filter
from pretix.base.templatetags.phone_format import phone_format
from pretix.presale.style import get_fonts

logger = logging.getLogger(__name__)


DEFAULT_VARIABLES = OrderedDict((
    ("secret", {
        "label": _("Ticket code (barcode content)"),
        "editor_sample": "tdmruoekvkpbv1o2mv8xccvqcikvr58u",
        "evaluate": lambda orderposition, order, event: (
            orderposition.secret[:30] + "…" if len(orderposition.secret) > 32 else orderposition.secret
        )
    }),
    ("order", {
        "label": _("Order code"),
        "editor_sample": "A1B2C",
        "evaluate": lambda orderposition, order, event: orderposition.order.code
    }),
    ("positionid", {
        "label": _("Order position number"),
        "editor_sample": "1",
        "evaluate": lambda orderposition, order, event: str(orderposition.positionid)
    }),
    ("item", {
        "label": _("Product name"),
        "editor_sample": _("Sample product"),
        "evaluate": lambda orderposition, order, event: str(orderposition.item.name)
    }),
    ("variation", {
        "label": _("Variation name"),
        "editor_sample": _("Sample variation"),
        "evaluate": lambda op, order, event: str(op.variation) if op.variation else ''
    }),
    ("item_description", {
        "label": _("Product description"),
        "editor_sample": _("Sample product description"),
        "evaluate": lambda orderposition, order, event: str(orderposition.item.description)
    }),
    ("itemvar", {
        "label": _("Product name and variation"),
        "editor_sample": _("Sample product – sample variation"),
        "evaluate": lambda orderposition, order, event: (
            '{} - {}'.format(orderposition.item.name, orderposition.variation)
            if orderposition.variation else str(orderposition.item.name)
        )
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
    ("price_with_addons", {
        "label": _("Price including add-ons"),
        "editor_sample": _("123.45 EUR"),
        "evaluate": lambda op, order, event: money_filter(op.price + sum(
            p.price
            for p in op.addons.all()
            if not p.canceled
        ), event.currency)
    }),
    ("attendee_name", {
        "label": _("Attendee name"),
        "editor_sample": _("John Doe"),
        "evaluate": lambda op, order, ev: op.attendee_name or (op.addon_to.attendee_name if op.addon_to else '')
    }),
    ("attendee_company", {
        "label": _("Attendee company"),
        "editor_sample": _("Sample company"),
        "evaluate": lambda op, order, ev: op.company or (op.addon_to.company if op.addon_to else '')
    }),
    ('attendee_address', {
        'label': _('Full attendee address'),
        'editor_sample': _('John Doe\nSample company\nSesame Street 42\n12345 Any City\nAtlantis'),
        'evaluate': lambda op, order, event: op.address_format()
    }),
    ("attendee_street", {
        "label": _("Attendee street"),
        "editor_sample": 'Sesame Street 42',
        "evaluate": lambda op, order, ev: op.street or (op.addon_to.street if op.addon_to else '')
    }),
    ("attendee_zipcode", {
        "label": _("Attendee ZIP code"),
        "editor_sample": '12345',
        "evaluate": lambda op, order, ev: op.zipcode or (op.addon_to.zipcode if op.addon_to else '')
    }),
    ("attendee_city", {
        "label": _("Attendee city"),
        "editor_sample": 'Any City',
        "evaluate": lambda op, order, ev: op.city or (op.addon_to.city if op.addon_to else '')
    }),
    ("attendee_state", {
        "label": _("Attendee state"),
        "editor_sample": 'Sample State',
        "evaluate": lambda op, order, ev: op.state or (op.addon_to.state if op.addon_to else '')
    }),
    ("attendee_country", {
        "label": _("Attendee country"),
        "editor_sample": 'Atlantis',
        "evaluate": lambda op, order, ev: str(getattr(op.country, 'name', '')) or (
            str(getattr(op.addon_to.country, 'name', '')) if op.addon_to else ''
        )
    }),
    ("event_name", {
        "label": _("Event name"),
        "editor_sample": _("Sample event name"),
        "evaluate": lambda op, order, ev: str(ev.name)
    }),
    ("event_series_name", {
        "label": _("Event series"),
        "editor_sample": _("Sample event name"),
        "evaluate": lambda op, order, ev: str(order.event.name)
    }),
    ("event_date", {
        "label": _("Event date"),
        "editor_sample": _("May 31st, 2017"),
        "evaluate": lambda op, order, ev: ev.get_date_from_display(show_times=False)
    }),
    ("event_date_range", {
        "label": _("Event date range"),
        "editor_sample": _("May 31st – June 4th, 2017"),
        "evaluate": lambda op, order, ev: ev.get_date_range_display(force_show_end=True)
    }),
    ("event_begin", {
        "label": _("Event begin date and time"),
        "editor_sample": _("2017-05-31 20:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_from.astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATETIME_FORMAT"
        ) if ev.date_from else ""
    }),
    ("event_begin_date", {
        "label": _("Event begin date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_from.astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATE_FORMAT"
        ) if ev.date_from else ""
    }),
    ("event_begin_time", {
        "label": _("Event begin time"),
        "editor_sample": _("20:00"),
        "evaluate": lambda op, order, ev: ev.get_time_from_display()
    }),
    ("event_end", {
        "label": _("Event end date and time"),
        "editor_sample": _("2017-05-31 22:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_to.astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATETIME_FORMAT"
        ) if ev.date_to else ""
    }),
    ("event_end_date", {
        "label": _("Event end date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_to.astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATE_FORMAT"
        ) if ev.date_to else ""
    }),
    ("event_end_time", {
        "label": _("Event end time"),
        "editor_sample": _("22:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_to.astimezone(timezone(ev.settings.timezone)),
            "TIME_FORMAT"
        ) if ev.date_to else ""
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
        "evaluate": lambda op, order, ev: str(ev.location)
    }),
    ("telephone", {
        "label": _("Phone number"),
        "editor_sample": "+01 1234 567890",
        "evaluate": lambda op, order, ev: phone_format(order.phone)
    }),
    ("invoice_name", {
        "label": _("Invoice address name"),
        "editor_sample": _("John Doe"),
        "evaluate": lambda op, order, ev: order.invoice_address.name if getattr(order, 'invoice_address', None) else ''
    }),
    ("invoice_company", {
        "label": _("Invoice address company"),
        "editor_sample": _("Sample company"),
        "evaluate": lambda op, order, ev: order.invoice_address.company if getattr(order, 'invoice_address', None) else ''
    }),
    ("invoice_street", {
        "label": _("Invoice address street"),
        "editor_sample": _("Sesame Street 42"),
        "evaluate": lambda op, order, ev: order.invoice_address.street if getattr(order, 'invoice_address', None) else ''
    }),
    ("invoice_zipcode", {
        "label": _("Invoice address ZIP code"),
        "editor_sample": _("12345"),
        "evaluate": lambda op, order, ev: order.invoice_address.zipcode if getattr(order, 'invoice_address', None) else ''
    }),
    ("invoice_city", {
        "label": _("Invoice address city"),
        "editor_sample": _("Sample city"),
        "evaluate": lambda op, order, ev: order.invoice_address.city if getattr(order, 'invoice_address', None) else ''
    }),
    ("invoice_state", {
        "label": _("Invoice address state"),
        "editor_sample": _("Sample State"),
        "evaluate": lambda op, order, ev: order.invoice_address.state if getattr(order, 'invoice_address', None) else ''
    }),
    ("invoice_country", {
        "label": _("Invoice address country"),
        "editor_sample": _("Atlantis"),
        "evaluate": lambda op, order, ev: str(getattr(order.invoice_address.country, 'name', '')) if getattr(order, 'invoice_address', None) else ''
    }),
    ("addons", {
        "label": _("List of Add-Ons"),
        "editor_sample": _("Add-on 1\nAdd-on 2"),
        "evaluate": lambda op, order, ev: "\n".join([
            '{} - {}'.format(p.item, p.variation) if p.variation else str(p.item)
            for p in (
                op.addons.all() if 'addons' in getattr(op, '_prefetched_objects_cache', {})
                else op.addons.select_related('item', 'variation')
            )
            if not p.canceled
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
    ("now_date", {
        "label": _("Printing date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: date_format(
            now().astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATE_FORMAT"
        )
    }),
    ("now_datetime", {
        "label": _("Printing date and time"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: date_format(
            now().astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATETIME_FORMAT"
        )
    }),
    ("now_time", {
        "label": _("Printing time"),
        "editor_sample": _("19:00"),
        "evaluate": lambda op, order, ev: date_format(
            now().astimezone(timezone(ev.settings.timezone)),
            "TIME_FORMAT"
        ) if ev.date_admission else ""
    }),
    ("seat", {
        "label": _("Seat: Full name"),
        "editor_sample": _("Ground floor, Row 3, Seat 4"),
        "evaluate": lambda op, order, ev: str(op.seat if op.seat else
                                              _('General admission') if ev.seating_plan_id is not None else "")
    }),
    ("seat_zone", {
        "label": _("Seat: zone"),
        "editor_sample": _("Ground floor"),
        "evaluate": lambda op, order, ev: str(op.seat.zone_name if op.seat else
                                              _('General admission') if ev.seating_plan_id is not None else "")
    }),
    ("seat_row", {
        "label": _("Seat: row"),
        "editor_sample": "3",
        "evaluate": lambda op, order, ev: str(op.seat.row_name if op.seat else "")
    }),
    ("seat_number", {
        "label": _("Seat: seat number"),
        "editor_sample": 4,
        "evaluate": lambda op, order, ev: str(op.seat.seat_number if op.seat else "")
    }),
))
DEFAULT_IMAGES = OrderedDict([])


@receiver(layout_image_variables, dispatch_uid="pretix_base_layout_image_variables_questions")
def images_from_questions(sender, *args, **kwargs):
    def get_answer(op, order, event, question_id, etag):
        a = None
        if op.addon_to:
            if 'answers' in getattr(op.addon_to, '_prefetched_objects_cache', {}):
                try:
                    a = [a for a in op.addon_to.answers.all() if a.question_id == question_id][0]
                except IndexError:
                    pass
            else:
                a = op.addon_to.answers.filter(question_id=question_id).first()

        if 'answers' in getattr(op, '_prefetched_objects_cache', {}):
            try:
                a = [a for a in op.answers.all() if a.question_id == question_id][0]
            except IndexError:
                pass
        else:
            a = op.answers.filter(question_id=question_id).first()

        if not a or not a.file or not any(a.file.name.lower().endswith(e) for e in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff")):
            return None
        else:
            if etag:
                return hashlib.sha1(a.file.name.encode()).hexdigest()
            return a.file

    d = {}
    for q in sender.questions.all():
        if q.type != Question.TYPE_FILE:
            continue
        d['question_{}'.format(q.identifier)] = {
            'label': _('Question: {question}').format(question=q.question),
            'evaluate': partial(get_answer, question_id=q.pk, etag=False),
            'etag': partial(get_answer, question_id=q.pk, etag=True),
        }
    return d


@receiver(layout_text_variables, dispatch_uid="pretix_base_layout_text_variables_questions")
def variables_from_questions(sender, *args, **kwargs):
    def get_answer(op, order, event, question_id):
        a = None
        if op.addon_to:
            if 'answers' in getattr(op.addon_to, '_prefetched_objects_cache', {}):
                try:
                    a = [a for a in op.addon_to.answers.all() if a.question_id == question_id][0]
                except IndexError:
                    pass
            else:
                a = op.addon_to.answers.filter(question_id=question_id).first()

        if 'answers' in getattr(op, '_prefetched_objects_cache', {}):
            try:
                a = [a for a in op.answers.all() if a.question_id == question_id][0]
            except IndexError:
                pass
        else:
            a = op.answers.filter(question_id=question_id).first()

        if not a:
            return ""
        else:
            return str(a)

    d = {}
    for q in sender.questions.all():
        if q.type == Question.TYPE_FILE:
            continue
        d['question_{}'.format(q.pk)] = {
            'label': _('Question: {question}').format(question=q.question),
            'editor_sample': _('<Answer: {question}>').format(question=q.question),
            'evaluate': partial(get_answer, question_id=q.pk)
        }
    return d


def _get_attendee_name_part(key, op, order, ev):
    if isinstance(key, tuple):
        return ' '.join(p for p in [_get_attendee_name_part(c[0], op, order, ev) for c in key] if p)
    return op.attendee_name_parts.get(key, '')


def _get_ia_name_part(key, op, order, ev):
    return order.invoice_address.name_parts.get(key, '') if getattr(order, 'invoice_address', None) else ''


def get_images(event):
    v = copy.copy(DEFAULT_IMAGES)

    for recv, res in layout_image_variables.send(sender=event):
        v.update(res)

    return v


def get_variables(event):
    v = copy.copy(DEFAULT_VARIABLES)

    scheme = PERSON_NAME_SCHEMES[event.settings.name_scheme]
    for key, label, weight in scheme['fields']:
        v['attendee_name_%s' % key] = {
            'label': _("Attendee name: {part}").format(part=label),
            'editor_sample': scheme['sample'][key],
            'evaluate': partial(_get_attendee_name_part, key)
        }
    for i in range(2, len(scheme['fields']) + 1):
        for comb in itertools.combinations(scheme['fields'], i):
            v['attendee_name_%s' % ('_'.join(c[0] for c in comb))] = {
                'label': _("Attendee name: {part}").format(part=' + '.join(str(c[1]) for c in comb)),
                'editor_sample': ' '.join(str(scheme['sample'][c[0]]) for c in comb),
                'evaluate': partial(_get_attendee_name_part, comb)
            }

    v['invoice_name']['editor_sample'] = scheme['concatenation'](scheme['sample'])
    v['attendee_name']['editor_sample'] = scheme['concatenation'](scheme['sample'])

    for key, label, weight in scheme['fields']:
        v['invoice_name_%s' % key] = {
            'label': _("Invoice address name: {part}").format(part=label),
            'editor_sample': scheme['sample'][key],
            "evaluate": partial(_get_ia_name_part, key)
        }

    for recv, res in layout_text_variables.send(sender=event):
        v.update(res)

    return v


class Renderer:

    def __init__(self, event, layout, background_file):
        self.layout = layout
        self.background_file = background_file
        self.variables = get_variables(event)
        self.images = get_images(event)
        self.event = event
        if self.background_file:
            self.bg_bytes = self.background_file.read()
            self.bg_pdf = PdfFileReader(BytesIO(self.bg_bytes), strict=False)
        else:
            self.bg_bytes = None
            self.bg_pdf = None

    @classmethod
    def _register_fonts(cls):
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

    def _draw_poweredby(self, canvas: Canvas, op: OrderPosition, o: dict):
        content = o.get('content', 'dark')
        if content not in ('dark', 'white'):
            content = 'dark'
        img = finders.find('pretixpresale/pdf/powered_by_pretix_{}.png'.format(content))

        ir = ThumbnailingImageReader(img)
        try:
            width, height = ir.resize(None, float(o['size']) * mm, 300)
        except:
            logger.exception("Can not resize image")
            pass
        canvas.drawImage(ir,
                         float(o['left']) * mm, float(o['bottom']) * mm,
                         width=width, height=height,
                         preserveAspectRatio=True, anchor='n',
                         mask='auto')

    def _draw_barcodearea(self, canvas: Canvas, op: OrderPosition, o: dict):
        content = o.get('content', 'secret')
        if content == 'secret':
            content = op.secret
        elif content == 'pseudonymization_id':
            content = op.pseudonymization_id

        level = 'H'
        if len(content) > 32:
            level = 'M'
        if len(content) > 128:
            level = 'L'
        reqs = float(o['size']) * mm
        qrw = QrCodeWidget(content, barLevel=level, barHeight=reqs, barWidth=reqs)
        d = Drawing(reqs, reqs)
        d.add(qrw)
        qr_x = float(o['left']) * mm
        qr_y = float(o['bottom']) * mm
        renderPDF.draw(d, canvas, qr_x, qr_y)

    def _get_ev(self, op, order):
        return op.subevent or order.event

    def _get_text_content(self, op: OrderPosition, order: Order, o: dict, inner=False):
        if o.get('locale', None) and not inner:
            with language(o['locale'], self.event.settings.region):
                return self._get_text_content(op, order, o, True)

        ev = self._get_ev(op, order)
        if not o['content']:
            return '(error)'
        if o['content'] == 'other':
            return o['text']
        elif o['content'].startswith('itemmeta:'):
            return op.item.meta_data.get(o['content'][9:]) or ''
        elif o['content'].startswith('meta:'):
            return ev.meta_data.get(o['content'][5:]) or ''
        elif o['content'] in self.variables:
            try:
                return self.variables[o['content']]['evaluate'](op, order, ev)
            except:
                logger.exception('Failed to process variable.')
                return '(error)'
        return ''

    def _draw_imagearea(self, canvas: Canvas, op: OrderPosition, order: Order, o: dict):
        ev = self._get_ev(op, order)
        if not o['content'] or o['content'] not in self.images:
            image_file = None
        else:
            try:
                image_file = self.images[o['content']]['evaluate'](op, order, ev)
            except:
                logger.exception('Failed to process variable.')
                image_file = None

        if image_file:
            ir = ThumbnailingImageReader(image_file)
            try:
                ir.resize(float(o['width']) * mm, float(o['height']) * mm, 300)
            except:
                logger.exception("Can not resize image")
                pass
            canvas.drawImage(
                image=ir,
                x=float(o['left']) * mm,
                y=float(o['bottom']) * mm,
                width=float(o['width']) * mm,
                height=float(o['height']) * mm,
                preserveAspectRatio=True,
                anchor='c',  # centered in frame
                mask='auto'
            )
        else:
            canvas.saveState()
            canvas.setFillColorRGB(.8, .8, .8, alpha=1)
            canvas.rect(
                x=float(o['left']) * mm,
                y=float(o['bottom']) * mm,
                width=float(o['width']) * mm,
                height=float(o['height']) * mm,
                stroke=0,
                fill=1,
            )
            canvas.restoreState()

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
        text = conditional_escape(
            self._get_text_content(op, order, o) or "",
        ).replace("\n", "<br/>\n")

        # reportlab does not support RTL, ligature-heavy scripts like Arabic. Therefore, we use ArabicReshaper
        # to resolve all ligatures and python-bidi to switch RTL texts.
        configuration = {
            'delete_harakat': True,
            'support_ligatures': False,
        }
        reshaper = ArabicReshaper(configuration=configuration)
        try:
            text = "<br/>".join(get_display(reshaper.reshape(l)) for l in text.split("<br/>"))
        except:
            logger.exception('Reshaping/Bidi fixes failed on string {}'.format(repr(text)))

        p = Paragraph(text, style=style)
        w, h = p.wrapOn(canvas, float(o['width']) * mm, 1000 * mm)
        # p_size = p.wrap(float(o['width']) * mm, 1000 * mm)
        ad = getAscentDescent(font, float(o['fontsize']))
        canvas.saveState()
        # The ascent/descent offsets here are not really proven to be correct, they're just empirical values to get
        # reportlab render similarly to browser canvas.
        if o.get('downward', False):
            canvas.translate(float(o['left']) * mm, float(o['bottom']) * mm)
            canvas.rotate(o.get('rotation', 0) * -1)
            p.drawOn(canvas, 0, -h - ad[1] / 2)
        else:
            canvas.translate(float(o['left']) * mm, float(o['bottom']) * mm + h)
            canvas.rotate(o.get('rotation', 0) * -1)
            p.drawOn(canvas, 0, -h - ad[1])
        canvas.restoreState()

    def draw_page(self, canvas: Canvas, order: Order, op: OrderPosition, show_page=True):
        for o in self.layout:
            if o['type'] == "barcodearea":
                self._draw_barcodearea(canvas, op, o)
            elif o['type'] == "imagearea":
                self._draw_imagearea(canvas, op, order, o)
            elif o['type'] == "textarea":
                self._draw_textarea(canvas, op, order, o)
            elif o['type'] == "poweredby":
                self._draw_poweredby(canvas, op, o)
            if self.bg_pdf:
                canvas.setPageSize((self.bg_pdf.getPage(0).mediaBox[2], self.bg_pdf.getPage(0).mediaBox[3]))
        if show_page:
            canvas.showPage()

    def render_background(self, buffer, title=_('Ticket')):
        if settings.PDFTK:
            buffer.seek(0)
            with tempfile.TemporaryDirectory() as d:
                with open(os.path.join(d, 'back.pdf'), 'wb') as f:
                    f.write(self.bg_bytes)
                with open(os.path.join(d, 'front.pdf'), 'wb') as f:
                    f.write(buffer.read())
                subprocess.run([
                    settings.PDFTK,
                    os.path.join(d, 'front.pdf'),
                    'background',
                    os.path.join(d, 'back.pdf'),
                    'output',
                    os.path.join(d, 'out.pdf'),
                    'compress'
                ], check=True)
                with open(os.path.join(d, 'out.pdf'), 'rb') as f:
                    return BytesIO(f.read())
        else:
            from PyPDF2 import PdfFileReader, PdfFileWriter
            buffer.seek(0)
            new_pdf = PdfFileReader(buffer)
            output = PdfFileWriter()

            for page in new_pdf.pages:
                bg_page = copy.copy(self.bg_pdf.getPage(0))
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
