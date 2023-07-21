#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Felix Schäfer
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import copy
import hashlib
import itertools
import json
import logging
import os
import re
import subprocess
import tempfile
import unicodedata
import uuid
from collections import OrderedDict, defaultdict
from functools import partial
from io import BytesIO

import jsonschema
import reportlab.rl_config
from bidi.algorithm import get_display
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.db.models import Max, Min
from django.db.models.fields.files import FieldFile
from django.dispatch import receiver
from django.utils.deconstruct import deconstructible
from django.utils.formats import date_format
from django.utils.html import conditional_escape
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext
from i18nfield.strings import LazyI18nString
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
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
from pretix.base.models import Order, OrderPosition, Question
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.base.signals import layout_image_variables, layout_text_variables
from pretix.base.templatetags.money import money_filter
from pretix.base.templatetags.phone_format import phone_format
from pretix.helpers.reportlab import ThumbnailingImageReader, reshaper
from pretix.presale.style import get_fonts

logger = logging.getLogger(__name__)

if not settings.DEBUG:
    reportlab.rl_config.shapeChecking = 0


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
    ("order_positionid", {
        "label": _("Order code and position number"),
        "editor_sample": "A1B2C-1",
        "evaluate": lambda orderposition, order, event: f"{orderposition.order.code}-{orderposition.positionid}"
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
    ("itemvar_description", {
        "label": _("Product variation description"),
        "editor_sample": _("Sample product variation description"),
        "evaluate": lambda orderposition, order, event: (
            str(orderposition.variation.description) if orderposition.variation else str(orderposition.item.description)
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
    ("attendee_email", {
        "label": _("Attendee email"),
        "editor_sample": 'foo@bar.com',
        "evaluate": lambda op, order, ev: op.attendee_email or (op.addon_to.attendee_email if op.addon_to else '')
    }),
    ("pseudonymization_id", {
        "label": _("Pseudonymization ID (lead scanning)"),
        "editor_sample": "GG89JUJDTA",
        "evaluate": lambda orderposition, order, event: orderposition.pseudonymization_id,
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
            ev.date_from.astimezone(ev.timezone),
            "SHORT_DATETIME_FORMAT"
        ) if ev.date_from else ""
    }),
    ("event_begin_date", {
        "label": _("Event begin date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_from.astimezone(ev.timezone),
            "SHORT_DATE_FORMAT"
        ) if ev.date_from else ""
    }),
    ("event_begin_time", {
        "label": _("Event begin time"),
        "editor_sample": _("20:00"),
        "evaluate": lambda op, order, ev: ev.get_time_from_display()
    }),
    ("event_begin_weekday", {
        "label": _("Event begin weekday"),
        "editor_sample": _("Friday"),
        "evaluate": lambda op, order, ev: ev.get_weekday_from_display()
    }),
    ("event_end", {
        "label": _("Event end date and time"),
        "editor_sample": _("2017-05-31 22:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_to.astimezone(ev.timezone),
            "SHORT_DATETIME_FORMAT"
        ) if ev.date_to else ""
    }),
    ("event_end_date", {
        "label": _("Event end date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_to.astimezone(ev.timezone),
            "SHORT_DATE_FORMAT"
        ) if ev.date_to else ""
    }),
    ("event_end_time", {
        "label": _("Event end time"),
        "editor_sample": _("22:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_to.astimezone(ev.timezone),
            "TIME_FORMAT"
        ) if ev.date_to else ""
    }),
    ("event_end_weekday", {
        "label": _("Event end weekday"),
        "editor_sample": _("Friday"),
        "evaluate": lambda op, order, ev: ev.get_weekday_to_display()
    }),
    ("event_admission", {
        "label": _("Event admission date and time"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_admission.astimezone(ev.timezone),
            "SHORT_DATETIME_FORMAT"
        ) if ev.date_admission else ""
    }),
    ("event_admission_time", {
        "label": _("Event admission time"),
        "editor_sample": _("19:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_admission.astimezone(ev.timezone),
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
        "evaluate": lambda op, order, ev: phone_format(order.phone, html=False)
    }),
    ("email", {
        "label": _("Email"),
        "editor_sample": "foo@bar.com",
        "evaluate": lambda op, order, ev: order.email
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
        "editor_sample": _("Add-on 1\n2x Add-on 2"),
        "evaluate": lambda op, order, ev: "\n".join([
            str(p) for p in generate_compressed_addon_list(op, order, ev)
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
    ("event_info_text", {
        "label": _("Event info text"),
        "editor_sample": _("Event info text"),
        "evaluate": lambda op, order, ev: str(order.event.settings.event_info_text)
    }),
    ("now_date", {
        "label": _("Printing date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: date_format(
            now().astimezone(ev.timezone),
            "SHORT_DATE_FORMAT"
        )
    }),
    ("now_datetime", {
        "label": _("Printing date and time"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: date_format(
            now().astimezone(ev.timezone),
            "SHORT_DATETIME_FORMAT"
        )
    }),
    ("now_time", {
        "label": _("Printing time"),
        "editor_sample": _("19:00"),
        "evaluate": lambda op, order, ev: date_format(
            now().astimezone(ev.timezone),
            "TIME_FORMAT"
        )
    }),
    ("valid_from_date", {
        "label": _("Validity start date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: date_format(
            op.valid_from.astimezone(ev.timezone),
            "SHORT_DATE_FORMAT"
        ) if op.valid_from else ""
    }),
    ("valid_from_datetime", {
        "label": _("Validity start date and time"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: date_format(
            op.valid_from.astimezone(ev.timezone),
            "SHORT_DATETIME_FORMAT"
        ) if op.valid_from else ""
    }),
    ("valid_from_time", {
        "label": _("Validity start time"),
        "editor_sample": _("19:00"),
        "evaluate": lambda op, order, ev: date_format(
            op.valid_from.astimezone(ev.timezone),
            "TIME_FORMAT"
        ) if op.valid_from else ""
    }),
    ("valid_until_date", {
        "label": _("Validity end date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: date_format(
            op.valid_until.astimezone(ev.timezone),
            "SHORT_DATE_FORMAT"
        ) if op.valid_until else ""
    }),
    ("valid_until_datetime", {
        "label": _("Validity end date and time"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: date_format(
            op.valid_until.astimezone(ev.timezone),
            "SHORT_DATETIME_FORMAT"
        ) if op.valid_until else ""
    }),
    ("valid_until_time", {
        "label": _("Validity end time"),
        "editor_sample": _("19:00"),
        "evaluate": lambda op, order, ev: date_format(
            op.valid_until.astimezone(ev.timezone),
            "TIME_FORMAT"
        ) if op.valid_until else ""
    }),
    ("medium_identifier", {
        "label": _("Reusable Medium ID"),
        "editor_sample": "ABC1234DEF4567",
        "evaluate": lambda op, order, ev: op.linked_media.all()[0].identifier if op.linked_media.all() else "",
    }),
    ("seat", {
        "label": _("Seat: Full name"),
        "editor_sample": _("Ground floor, Row 3, Seat 4"),
        "evaluate": lambda op, order, ev: str(get_seat(op) if get_seat(op) else
                                              _('General admission') if ev.seating_plan_id is not None else "")
    }),
    ("seat_zone", {
        "label": _("Seat: zone"),
        "editor_sample": _("Ground floor"),
        "evaluate": lambda op, order, ev: str(get_seat(op).zone_name if get_seat(op) else
                                              _('General admission') if ev.seating_plan_id is not None else "")
    }),
    ("seat_row", {
        "label": _("Seat: row"),
        "editor_sample": "3",
        "evaluate": lambda op, order, ev: str(get_seat(op).row_name if get_seat(op) else "")
    }),
    ("seat_number", {
        "label": _("Seat: seat number"),
        "editor_sample": 4,
        "evaluate": lambda op, order, ev: str(get_seat(op).seat_number if get_seat(op) else "")
    }),
    ("first_scan", {
        "label": _("Date and time of first scan"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: get_first_scan(op)
    }),
    ("giftcard_issuance_date", {

        "label": _("Gift card: Issuance date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: get_giftcard_issuance(op, ev)
    }),
    ("giftcard_expiry_date", {
        "label": _("Gift card: Expiration date"),
        "editor_sample": _("2017-05-31"),
        "evaluate": lambda op, order, ev: get_giftcard_expiry(op, ev)
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
            a = op.answers.filter(question_id=question_id).first() or a

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
            a = op.answers.filter(question_id=question_id).first() or a

        if not a:
            return ""
        else:
            return str(a)

    d = {}
    for q in sender.questions.all():
        if q.type == Question.TYPE_FILE:
            continue
        d['question_{}'.format(q.identifier)] = {
            'label': _('Question: {question}').format(question=q.question),
            'editor_sample': _('<Answer: {question}>').format(question=q.question),
            'evaluate': partial(get_answer, question_id=q.pk),
            'migrate_from': 'question_{}'.format(q.pk)
        }
        d['question_{}'.format(q.pk)] = {
            'label': _('Question: {question}').format(question=q.question),
            'editor_sample': _('<Answer: {question}>').format(question=q.question),
            'evaluate': partial(get_answer, question_id=q.pk),
            'hidden': True,
        }
    return d


def _get_attendee_name_part(key, op, order, ev):
    name_parts = op.attendee_name_parts or (op.addon_to.attendee_name_parts if op.addon_to else {})
    if isinstance(key, tuple):
        parts = [_get_attendee_name_part(c[0], op, order, ev) for c in key if not (c[0] == 'salutation' and name_parts.get(c[0], '') == "Mx")]
        return ' '.join(p for p in parts if p)
    value = name_parts.get(key, '')
    if key == 'salutation':
        return pgettext('person_name_salutation', value)
    return value


def _get_ia_name_part(key, op, order, ev):
    value = order.invoice_address.name_parts.get(key, '') if getattr(order, 'invoice_address', None) else ''
    if key == 'salutation' and value:
        return pgettext('person_name_salutation', value)
    return value


def get_images(event):
    v = copy.copy(DEFAULT_IMAGES)

    for recv, res in layout_image_variables.send(sender=event):
        v.update(res)

    return v


def get_variables(event):
    v = copy.copy(DEFAULT_VARIABLES)

    scheme = PERSON_NAME_SCHEMES[event.settings.name_scheme]

    concatenation_for_salutation = scheme.get("concatenation_for_salutation", scheme["concatenation"])
    v['attendee_name_for_salutation'] = {
        'label': _("Attendee name for salutation"),
        'editor_sample': _("Mr Doe"),
        'evaluate': lambda op, order, ev: concatenation_for_salutation(op.attendee_name_parts or (op.addon_to.attendee_name_parts if op.addon_to else {}))
    }

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

    v['invoice_name_for_salutation'] = {
        'label': _("Invoice address name for salutation"),
        'editor_sample': _("Mr Doe"),
        'evaluate': lambda op, order, ev: concatenation_for_salutation(order.invoice_address.name_parts if getattr(order, 'invoice_address', None) else {})
    }

    for key, label, weight in scheme['fields']:
        v['invoice_name_%s' % key] = {
            'label': _("Invoice address name: {part}").format(part=label),
            'editor_sample': scheme['sample'][key],
            "evaluate": partial(_get_ia_name_part, key)
        }

    for recv, res in layout_text_variables.send(sender=event):
        v.update(res)

    return v


def get_giftcard_expiry(op: OrderPosition, ev):
    if not op.item.issue_giftcard:
        return ""  # performance optimization
    m = op.issued_gift_cards.aggregate(m=Min('expires'))['m']
    if not m:
        return ""
    return date_format(m.astimezone(ev.timezone), "SHORT_DATE_FORMAT")


def get_giftcard_issuance(op: OrderPosition, ev):
    if not op.item.issue_giftcard:
        return ""  # performance optimization
    m = op.issued_gift_cards.aggregate(m=Max('issuance'))['m']
    if not m:
        return ""
    return date_format(m.astimezone(ev.timezone), "SHORT_DATE_FORMAT")


def get_first_scan(op: OrderPosition):
    scans = list(op.checkins.all())

    if scans:
        return date_format(
            list(op.checkins.all())[-1].datetime.astimezone(op.order.event.timezone),
            "SHORT_DATETIME_FORMAT"
        )
    return ""


def get_seat(op: OrderPosition):
    if op.seat_id:
        return op.seat
    if op.addon_to_id:
        return op.addon_to.seat
    return None


def generate_compressed_addon_list(op, order, event):
    itemcount = defaultdict(int)
    addons = (
        op.addons.all() if 'addons' in getattr(op, '_prefetched_objects_cache', {})
        else op.addons.select_related('item', 'variation')
    )
    for pos in addons:
        itemcount[pos.item, pos.variation] += 1

    addonlist = []
    for (item, variation), count in itemcount.items():
        if variation:
            if count > 1:
                addonlist.append('{}x {} - {}'.format(count, item.name, variation.value))
            else:
                addonlist.append('{} - {}'.format(item.name, variation.value))
        else:
            if count > 1:
                addonlist.append('{}x {}'.format(count, item.name))
            else:
                addonlist.append(item.name)
    return addonlist


class Renderer:

    def __init__(self, event, layout, background_file):
        self.layout = layout
        self.background_file = background_file
        self.variables = get_variables(event)
        self.images = get_images(event)
        self.event = event
        if self.background_file:
            self.bg_bytes = self.background_file.read()
            self.bg_pdf = PdfReader(BytesIO(self.bg_bytes), strict=False)
        else:
            self.bg_bytes = None
            self.bg_pdf = None

    @classmethod
    def _register_fonts(cls):
        if hasattr(cls, '_fonts_registered'):
            return
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

        cls._fonts_registered = True

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

    def _draw_barcodearea(self, canvas: Canvas, op: OrderPosition, order: Order, o: dict):
        content = o.get('content', 'secret')
        if content == 'secret':
            # do not use get_text_content because it uses a shortened version of secret
            # and does not deal with our default value here properly
            content = op.secret
        else:
            content = self._get_text_content(op, order, o)

        if len(content) == 0:
            return

        level = 'H'
        if len(content) > 32:
            level = 'M'
        if len(content) > 128:
            level = 'L'
        reqs = float(o['size']) * mm
        kwargs = {}
        if o.get('nowhitespace', False):
            kwargs['barBorder'] = 0
        qrw = QrCodeWidget(content, barLevel=level, barHeight=reqs, barWidth=reqs, **kwargs)
        d = Drawing(reqs, reqs)
        d.add(qrw)
        qr_x = float(o['left']) * mm
        qr_y = float(o['bottom']) * mm
        renderPDF.draw(d, canvas, qr_x, qr_y)

        # Add QR content + PDF issuer as a hidden string (fully transparent & very very small)
        # This helps automated processing of the PDF file by 3rd parties, e.g. when checking tickets for resale
        data = {
            "issuer": settings.SITE_URL,
            o.get('content', 'secret'): content
        }
        canvas.saveState()
        canvas.setFont('Open Sans', .01)
        canvas.setFillColorRGB(0, 0, 0, 0)
        canvas.drawString(0 * mm, 0 * mm, json.dumps(data, sort_keys=True))
        canvas.restoreState()

    def _get_ev(self, op, order):
        return op.subevent or order.event

    def _get_text_content(self, op: OrderPosition, order: Order, o: dict, inner=False):
        if o.get('locale', None) and not inner:
            with language(o['locale'], self.event.settings.region):
                return self._get_text_content(op, order, o, True)

        ev = self._get_ev(op, order)

        if not o['content']:
            return '(error)'

        if o['content'] == 'other' or o['content'] == 'other_i18n':
            if o['content'] == 'other_i18n':
                text = str(LazyI18nString(o.get('text_i18n', {})))
            else:
                text = o.get('text', '')

            def replace(x):
                if x.group(1).startswith('itemmeta:'):
                    if op.variation_id:
                        return op.variation.meta_data.get(x.group(1)[9:]) or ''
                    return op.item.meta_data.get(x.group(1)[9:]) or ''
                elif x.group(1).startswith('meta:'):
                    return ev.meta_data.get(x.group(1)[5:]) or ''
                elif x.group(1) not in self.variables:
                    return x.group(0)
                if x.group(1) == 'secret':
                    # Do not use shortened version
                    return op.secret

                try:
                    return self.variables[x.group(1)]['evaluate'](op, order, ev)
                except:
                    logger.exception('Failed to process variable.')
                    return '(error)'

            # We do not use str.format like in emails so we (a) can evaluate lazily and (b) can re-implement this
            # 1:1 on other platforms that render PDFs through our API (libpretixprint)
            return re.sub(r'\{([a-zA-Z0-9:_]+)\}', replace, text)

        elif o['content'].startswith('itemmeta:'):
            if op.variation_id:
                return op.variation.meta_data.get(o['content'][9:]) or ''
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
            try:
                ir = ThumbnailingImageReader(image_file)
                ir.resize(float(o['width']) * mm, float(o['height']) * mm, 300)
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
                if isinstance(image_file, FieldFile):
                    # ThumbnailingImageReader "closes" the file, so it's no use to use the same file pointer
                    # in case we need it again. For FieldFile, fortunately, there is an easy way to make the file
                    # refresh itself when it is used next.
                    del image_file.file
            except:
                logger.exception("Can not load or resize image")
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

        try:
            ad = getAscentDescent(font, float(o['fontsize']))
        except KeyError:  # font not known, fall back
            logger.warning(f'Use of unknown font "{font}"')
            font = 'Open Sans'
            ad = getAscentDescent(font, float(o['fontsize']))

        align_map = {
            'left': TA_LEFT,
            'center': TA_CENTER,
            'right': TA_RIGHT
        }
        # lineheight display differs from browser canvas. This calc is just empirical values to get
        # reportlab render similarly to browser canvas.
        # for backwards compatability use „uncorrected“ lineheight of 1.0 instead of 1.15
        lineheight = float(o['lineheight']) * 1.15 if 'lineheight' in o else 1.0
        style = ParagraphStyle(
            name=uuid.uuid4().hex,
            fontName=font,
            fontSize=float(o['fontsize']),
            leading=lineheight * float(o['fontsize']),
            # for backwards compatability use autoLeading if no lineheight is given
            autoLeading='off' if 'lineheight' in o else 'max',
            textColor=Color(o['color'][0] / 255, o['color'][1] / 255, o['color'][2] / 255),
            alignment=align_map[o['align']]
        )
        # add an almost-invisible space &hairsp; after hyphens as word-wrap in ReportLab only works on space chars
        text = conditional_escape(
            self._get_text_content(op, order, o) or "",
        ).replace("\n", "<br/>\n").replace("-", "-&hairsp;")

        # reportlab does not support unicode combination characters
        # It's important we do this before we use ArabicReshaper
        text = unicodedata.normalize("NFC", text)

        # reportlab does not support RTL, ligature-heavy scripts like Arabic. Therefore, we use ArabicReshaper
        # to resolve all ligatures and python-bidi to switch RTL texts.
        try:
            text = "<br/>".join(get_display(reshaper.reshape(l)) for l in text.split("<br/>"))
        except:
            logger.exception('Reshaping/Bidi fixes failed on string {}'.format(repr(text)))

        p = Paragraph(text, style=style)
        w, h = p.wrapOn(canvas, float(o['width']) * mm, 1000 * mm)
        # p_size = p.wrap(float(o['width']) * mm, 1000 * mm)
        canvas.saveState()
        # The ascent/descent offsets here are not really proven to be correct, they're just empirical values to get
        # reportlab render similarly to browser canvas.
        if o.get('downward', False):
            canvas.translate(float(o['left']) * mm, float(o['bottom']) * mm)
            canvas.rotate(o.get('rotation', 0) * -1)
            p.drawOn(canvas, 0, -h - ad[1] / 2.5)
        else:
            if lineheight != 1.0:
                # lineheight adds to ascent/descent offsets, just empirical values again to get
                # reportlab to render similarly to browser canvas
                ad = (
                    ad[0],
                    ad[1] + (lineheight - 1.0) * float(o['fontsize']) * 1.05
                )
            canvas.translate(float(o['left']) * mm, float(o['bottom']) * mm + h)
            canvas.rotate(o.get('rotation', 0) * -1)
            p.drawOn(canvas, 0, -h - ad[1])
        canvas.restoreState()

    def draw_page(self, canvas: Canvas, order: Order, op: OrderPosition, show_page=True, only_page=None):
        page_count = len(self.bg_pdf.pages)

        if not only_page and not show_page:
            raise ValueError("only_page=None and show_page=False cannot be combined")

        for page in range(page_count):
            if only_page and only_page != page + 1:
                continue
            for o in self.layout:
                if o.get('page', 1) != page + 1:
                    continue
                if o['type'] == "barcodearea":
                    self._draw_barcodearea(canvas, op, order, o)
                elif o['type'] == "imagearea":
                    self._draw_imagearea(canvas, op, order, o)
                elif o['type'] == "textarea":
                    self._draw_textarea(canvas, op, order, o)
                elif o['type'] == "poweredby":
                    self._draw_poweredby(canvas, op, o)
                if self.bg_pdf:
                    page_size = (
                        self.bg_pdf.pages[0].mediabox[2] - self.bg_pdf.pages[0].mediabox[0],
                        self.bg_pdf.pages[0].mediabox[3] - self.bg_pdf.pages[0].mediabox[1]
                    )
                    if self.bg_pdf.pages[0].get('/Rotate') in (90, 270):
                        # swap dimensions due to pdf being rotated
                        page_size = page_size[::-1]
                    canvas.setPageSize(page_size)
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
                    'multibackground',
                    os.path.join(d, 'back.pdf'),
                    'output',
                    os.path.join(d, 'out.pdf'),
                    'compress'
                ], check=True)
                with open(os.path.join(d, 'out.pdf'), 'rb') as f:
                    return BytesIO(f.read())
        else:
            buffer.seek(0)
            new_pdf = PdfReader(buffer)
            output = PdfWriter()

            for i, page in enumerate(new_pdf.pages):
                bg_page = copy.deepcopy(self.bg_pdf.pages[i])
                bg_rotation = bg_page.get('/Rotate')
                if bg_rotation:
                    # /Rotate is clockwise, transformation.rotate is counter-clockwise
                    t = Transformation().rotate(bg_rotation)
                    w = float(page.mediabox.getWidth())
                    h = float(page.mediabox.getHeight())
                    if bg_rotation in (90, 270):
                        # offset due to rotation base
                        if bg_rotation == 90:
                            t = t.translate(h, 0)
                        else:
                            t = t.translate(0, w)
                        # rotate mediabox as well
                        page.mediabox = RectangleObject((
                            page.mediabox.left.as_numeric(),
                            page.mediabox.bottom.as_numeric(),
                            page.mediabox.top.as_numeric(),
                            page.mediabox.right.as_numeric(),
                        ))
                        page.trimbox = page.mediabox
                    elif bg_rotation == 180:
                        t = t.translate(w, h)
                    page.add_transformation(t)
                bg_page.merge_page(page)
                output.add_page(bg_page)

            output.add_metadata({
                '/Title': str(title),
                '/Creator': 'pretix',
            })
            outbuffer = BytesIO()
            output.write(outbuffer)
            outbuffer.seek(0)
            return outbuffer


def merge_background(fg_pdf, bg_pdf, out_file, compress):
    if settings.PDFTK:
        with tempfile.TemporaryDirectory() as d:
            fg_filename = os.path.join(d, 'fg.pdf')
            bg_filename = os.path.join(d, 'bg.pdf')
            fg_pdf.write(fg_filename)
            bg_pdf.write(bg_filename)
            pdftk_cmd = [
                settings.PDFTK,
                fg_filename,
                'multibackground',
                bg_filename,
                'output',
                '-',
            ]
            if compress:
                pdftk_cmd.append('compress')
            subprocess.run(pdftk_cmd, check=True, stdout=out_file)
    else:
        output = PdfWriter()
        for i, page in enumerate(fg_pdf.pages):
            bg_page = copy.deepcopy(bg_pdf.pages[i])
            bg_rotation = bg_page.get('/Rotate')
            if bg_rotation:
                # /Rotate is clockwise, transformation.rotate is counter-clockwise
                t = Transformation().rotate(bg_rotation)
                w = float(page.mediabox.getWidth())
                h = float(page.mediabox.getHeight())
                if bg_rotation in (90, 270):
                    # offset due to rotation base
                    if bg_rotation == 90:
                        t = t.translate(h, 0)
                    else:
                        t = t.translate(0, w)
                    # rotate mediabox as well
                    page.mediabox = RectangleObject((
                        page.mediabox.left.as_numeric(),
                        page.mediabox.bottom.as_numeric(),
                        page.mediabox.top.as_numeric(),
                        page.mediabox.right.as_numeric(),
                    ))
                    page.trimbox = page.mediabox
                elif bg_rotation == 180:
                    t = t.translate(w, h)
                page.add_transformation(t)
            bg_page.merge_page(page)
            output.add_page(bg_page)
        output.write(out_file)


@deconstructible
class PdfLayoutValidator:
    def __call__(self, value):
        if not isinstance(value, dict):
            try:
                val = json.loads(value)
            except ValueError:
                raise ValidationError(_('Your layout file is not a valid JSON file.'))
        else:
            val = value
        with open(finders.find('schema/pdf-layout.schema.json'), 'r') as f:
            schema = json.loads(f.read())
        try:
            jsonschema.validate(val, schema)
        except jsonschema.ValidationError as e:
            e = str(e).replace('%', '%%')
            raise ValidationError(_('Your layout file is not a valid layout. Error message: {}').format(e))
