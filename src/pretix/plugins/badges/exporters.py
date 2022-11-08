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
# This file contains Apache-licensed contributions copyrighted by: pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import json
import logging
from collections import OrderedDict
from datetime import datetime, time, timedelta
from io import BytesIO
from typing import Tuple

import dateutil.parser
from django import forms
from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import DataError, models
from django.db.models import Exists, OuterRef, Q, Subquery
from django.db.models.functions import Cast, Coalesce
from django.utils.timezone import make_aware
from django.utils.translation import gettext as _, gettext_lazy
from PyPDF2 import PdfMerger, PdfReader, PdfWriter, Transformation
from PyPDF2.generic import RectangleObject
from reportlab.lib import pagesizes
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from pretix.base.exporter import BaseExporter
from pretix.base.i18n import language
from pretix.base.models import Order, OrderPosition, Question, QuestionAnswer
from pretix.base.pdf import Renderer
from pretix.base.services.export import ExportError
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.helpers.templatetags.jsonfield import JSONExtract
from pretix.plugins.badges.models import BadgeItem, BadgeLayout

logger = logging.getLogger(__name__)


def _renderer(event, layout):
    if layout is None:
        return None
    if isinstance(layout.background, File) and layout.background.name:
        bgf = default_storage.open(layout.background.name, "rb")
    else:
        bgf = open(finders.find('pretixplugins/badges/badge_default_a6l.pdf'), "rb")
    return Renderer(event, json.loads(layout.layout), bgf)


OPTIONS = OrderedDict([
    ('one', {
        'name': gettext_lazy('One badge per page'),
        'cols': 1,
        'rows': 1,
        'margins': [0, 0, 0, 0],
        'offsets': [0, 0],
        'pagesize': None,
    }),
    ('a4_a6l', {
        'name': gettext_lazy('4 landscape A6 pages on one A4 page'),
        'cols': 2,
        'rows': 2,
        'margins': [0 * mm, 0 * mm, 0 * mm, 0 * mm],
        'offsets': [pagesizes.landscape(pagesizes.A4)[0] / 2, pagesizes.landscape(pagesizes.A4)[1] / 2],
        'pagesize': pagesizes.landscape(pagesizes.A4),
    }),
    ('a4_a6p', {
        'name': gettext_lazy('4 portrait A6 pages on one A4 page'),
        'cols': 2,
        'rows': 2,
        'margins': [0 * mm, 0 * mm, 0 * mm, 0 * mm],
        'offsets': [pagesizes.portrait(pagesizes.A4)[0] / 2, pagesizes.portrait(pagesizes.A4)[1] / 2],
        'pagesize': pagesizes.portrait(pagesizes.A4),
    }),
    ('a4_a7l', {
        'name': gettext_lazy('8 landscape A7 pages on one A4 page'),
        'cols': 2,
        'rows': 4,
        'margins': [0 * mm, 0 * mm, 0 * mm, 0 * mm],
        'offsets': [pagesizes.portrait(pagesizes.A4)[0] / 2, pagesizes.portrait(pagesizes.A4)[1] / 4],
        'pagesize': pagesizes.portrait(pagesizes.A4),
    }),
    ('a4_a7p', {
        'name': gettext_lazy('8 portrait A7 pages on one A4 page'),
        'cols': 4,
        'rows': 2,
        'margins': [0 * mm, 0 * mm, 0 * mm, 0 * mm],
        'offsets': [pagesizes.landscape(pagesizes.A4)[0] / 4, pagesizes.landscape(pagesizes.A4)[1] / 2],
        'pagesize': pagesizes.landscape(pagesizes.A4),
    }),
    ('durable_54x90', {
        'name': 'DURABLE BADGEMAKER® 54 x 90 mm (1445-02)',
        'cols': 2,
        'rows': 5,
        'margins': [12 * mm, 15 * mm, 15 * mm, 15 * mm],
        'offsets': [90 * mm, 54 * mm],
        'pagesize': pagesizes.A4,
    }),
    ('durable_40x75', {
        'name': 'DURABLE BADGEMAKER® 40 x 75 mm (1453-02)',
        'cols': 2,
        'rows': 6,
        'margins': [28.5 * mm, 30 * mm, 28.5 * mm, 30 * mm],
        'offsets': [75 * mm, 40 * mm],
        'pagesize': pagesizes.A4,
    }),
    ('durable_60x90', {
        'name': 'DURABLE BADGEMAKER® 60 x 90 mm (1456-02)',
        'cols': 2,
        'rows': 4,
        'margins': [28.5 * mm, 15 * mm, 28.5 * mm, 15 * mm],
        'offsets': [90 * mm, 60 * mm],
        'pagesize': pagesizes.A4,
    }),
    ('durable_fix_40x75', {
        'name': 'DURABLE BADGEFIX® 40 x 75 mm (8334-02)',
        'cols': 2,
        'rows': 6,
        'margins': [28.5 * mm, 30 * mm, 28.5 * mm, 30 * mm],
        'offsets': [93 * mm, 60 * mm],
        'pagesize': pagesizes.A4,
    }),
    ('herma_50x80', {
        'name': 'HERMA 50 x 80 mm (4412)',
        'cols': 2,
        'rows': 5,
        'margins': [13.5 * mm, 17.5 * mm, 13.5 * mm, 17.5 * mm],
        'offsets': [95 * mm, 55 * mm],
        'pagesize': pagesizes.A4,
    }),
    ('herma_40x40', {
        'name': 'HERMA 40 x 40 mm (9642)',
        'cols': 4,
        'rows': 6,
        'margins': [13.5 * mm, 15 * mm, 13.5 * mm, 15 * mm],
        'offsets': [46 * mm, 46 * mm],
        'pagesize': pagesizes.A4,
    }),
])


def render_pdf(event, positions, opt):
    Renderer._register_fonts()

    renderermap = {
        bi.item_id: _renderer(event, bi.layout)
        for bi in BadgeItem.objects.select_related('layout').filter(item__event=event)
    }
    try:
        default_renderer = _renderer(event, event.badge_layouts.get(default=True))
    except BadgeLayout.DoesNotExist:
        default_renderer = None

    op_renderers = [(op, renderermap.get(op.item_id, default_renderer)) for op in positions if renderermap.get(op.item_id, default_renderer)]
    if not len(op_renderers):
        raise ExportError(_("None of the selected products is configured to print badges."))

    # render each badge on its own page first
    merger = PdfMerger()
    merger.add_metadata({
        '/Title': 'Badges',
        '/Creator': 'pretix',
    })
    for op, renderer in op_renderers:
        buffer = BytesIO()
        page = canvas.Canvas(buffer, pagesize=pagesizes.A4)
        with language(op.order.locale, op.order.event.settings.region):
            renderer.draw_page(page, op.order, op)

        if opt['pagesize']:
            page.setPageSize(opt['pagesize'])
        page.save()
        buffer = renderer.render_background(buffer, _('Badge'))
        merger.append(ContentFile(buffer.read()))

    outbuffer = BytesIO()
    merger.write(outbuffer)
    outbuffer.seek(0)

    badges_per_page = opt['cols'] * opt['rows']
    if badges_per_page == 1:
        # no need to place multiple badges on one page
        return outbuffer

    # place n-up badges/pages per page
    badges_pdf = PdfReader(outbuffer)
    nup_pdf = PdfWriter()
    nup_page = None
    for i, page in enumerate(badges_pdf.pages):
        di = i % badges_per_page
        if di == 0:
            nup_page = nup_pdf.add_blank_page(
                width=opt['pagesize'][0],
                height=opt['pagesize'][1],
            )
        tx = opt['margins'][3] + (di % opt['cols']) * opt['offsets'][0]
        ty = opt['margins'][2] + (opt['rows'] - 1 - (di // opt['cols'])) * opt['offsets'][1]
        page.add_transformation(Transformation().translate(tx, ty))
        page.mediabox = RectangleObject((
            page.mediabox.left.as_numeric() + tx,
            page.mediabox.bottom.as_numeric() + ty,
            page.mediabox.right.as_numeric() + tx,
            page.mediabox.top.as_numeric() + ty
        ))
        page.trimbox = page.mediabox
        nup_page.merge_page(page)

    outbuffer = BytesIO()
    nup_pdf.write(outbuffer)
    outbuffer.seek(0)

    return outbuffer


class BadgeExporter(BaseExporter):
    identifier = "badges"
    verbose_name = _("Attendee badges")

    @property
    def export_form_fields(self):
        name_scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme]
        d = OrderedDict(
            [
                ('items',
                 forms.ModelMultipleChoiceField(
                     queryset=self.event.items.annotate(
                         no_badging=Exists(BadgeItem.objects.filter(item=OuterRef('pk'), layout__isnull=True))
                     ).exclude(no_badging=True),
                     label=_('Limit to products'),
                     widget=forms.CheckboxSelectMultiple(
                         attrs={'class': 'scrolling-multiple-choice'}
                     ),
                     initial=self.event.items.filter(admission=True)
                 )),
                ('include_pending',
                 forms.BooleanField(
                     label=_('Include pending orders'),
                     required=False
                 )),
                ('include_addons',
                 forms.BooleanField(
                     label=_('Include add-on or bundled positions'),
                     required=False
                 )),
                ('rendering',
                 forms.ChoiceField(
                     label=_('Rendering option'),
                     choices=[
                         (k, r['name']) for k, r in OPTIONS.items()
                     ],
                     required=True,
                     help_text=_('This option allows you to align multiple badges on one page, for example if you '
                                 'want to print to a sheet of stickers with a regular office printer. Please note '
                                 'that your individual badge layouts must already be in the correct size.')
                 )),
                ('date_from',
                 forms.DateField(
                     label=_('Start date'),
                     widget=forms.DateInput(attrs={'class': 'datepickerfield'}),
                     required=False,
                     help_text=_('Only include tickets for dates on or after this date.')
                 )),
                ('date_to',
                 forms.DateField(
                     label=_('End date'),
                     widget=forms.DateInput(attrs={'class': 'datepickerfield'}),
                     required=False,
                     help_text=_('Only include tickets for dates on or before this date.')
                 )),
                ('order_by',
                 forms.ChoiceField(
                     label=_('Sort by'),
                     choices=[
                         ('name', _('Attendee name')),
                         ('code', _('Order code')),
                         ('date', _('Event date')),
                     ] + ([
                         ('name:{}'.format(k), _('Attendee name: {part}').format(part=label))
                         for k, label, w in name_scheme['fields']
                     ] if len(name_scheme['fields']) > 1 else []) + ([
                         ('question:{}'.format(q.identifier), _('Question: {question}').format(question=q.question))
                         for q in self.event.questions.filter(type__in=(
                             # All except TYPE_FILE and future ones
                             Question.TYPE_TIME, Question.TYPE_TEXT, Question.TYPE_DATE, Question.TYPE_BOOLEAN,
                             Question.TYPE_COUNTRYCODE, Question.TYPE_DATETIME, Question.TYPE_NUMBER,
                             Question.TYPE_PHONENUMBER, Question.TYPE_STRING, Question.TYPE_CHOICE,
                             Question.TYPE_CHOICE_MULTIPLE
                         ))
                     ] if not self.is_multievent else []),
                 )),
            ]
        )
        return d

    def render(self, form_data: dict) -> Tuple[str, str, str]:
        qs = OrderPosition.objects.filter(
            order__event=self.event, item_id__in=form_data['items']
        ).prefetch_related(
            'answers', 'answers__question'
        ).select_related('order', 'item', 'variation', 'addon_to')

        if not form_data.get('include_addons'):
            qs = qs.filter(addon_to__isnull=True)

        if form_data.get('include_pending'):
            qs = qs.filter(order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING])
        else:
            qs = qs.filter(order__status__in=[Order.STATUS_PAID])

        if form_data.get('date_from'):
            dt = make_aware(datetime.combine(
                dateutil.parser.parse(form_data['date_from']).date(),
                time(hour=0, minute=0, second=0)
            ), self.event.timezone)
            qs = qs.filter(Q(subevent__date_from__gte=dt) | Q(subevent__isnull=True, order__event__date_from__gte=dt))

        if form_data.get('date_to'):
            dt = make_aware(datetime.combine(
                dateutil.parser.parse(form_data['date_to']).date() + timedelta(days=1),
                time(hour=0, minute=0, second=0)
            ), self.event.timezone)
            qs = qs.filter(Q(subevent__date_from__lt=dt) | Q(subevent__isnull=True, order__event__date_from__lt=dt))

        if form_data.get('order_by') == 'name':
            qs = qs.order_by('attendee_name_cached', 'order__code')
        elif form_data.get('order_by') == 'code':
            qs = qs.order_by('order__code')
        elif form_data.get('order_by') == 'date':
            qs = qs.annotate(ed=Coalesce('subevent__date_from', 'order__event__date_from')).order_by('ed', 'order__code')
        elif form_data.get('order_by', '').startswith('name:'):
            part = form_data['order_by'][5:]
            qs = qs.annotate(
                resolved_name=Coalesce('attendee_name_parts', 'addon_to__attendee_name_parts',
                                       'order__invoice_address__name_parts')
            ).annotate(
                resolved_name_part=JSONExtract('resolved_name', part)
            ).order_by(
                'resolved_name_part'
            )
        elif form_data.get('order_by', '').startswith('question:'):
            part = form_data['order_by'].split(':', 1)[1]
            question = self.event.questions.get(identifier=part)
            if question.type == Question.TYPE_NUMBER:
                # We use a database-level type cast to sort numbers like 1, 2, 10, 11 and not like 1, 10, 11, 2.
                # This works perfectly fine e.g. on SQLite where an invalid number will be casted to 0, but will
                # raise a DataError on PostgreSQL if there is a non-number in the data.
                question_subquery = Subquery(
                    QuestionAnswer.objects.filter(
                        orderposition_id=OuterRef('pk'),
                        question_id=question.pk,
                    ).annotate(
                        converted_answer=Cast('answer', output_field=models.FloatField())
                    ).order_by().values('converted_answer')[:1]
                )
            elif question.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
                # Sorting by choice questions must be handled differently because the QuestionAnswer.value
                # attribute may be dependent on the submitters locale, which we don't want here. So we sort by
                # order of the position instead. In case of multiple choice, the first selected order counts, which
                # is not perfect but better than no sorting at all.
                question_subquery = Subquery(
                    QuestionAnswer.options.through.objects.filter(
                        questionanswer__orderposition_id=OuterRef('pk'),
                        questionanswer__question_id=question.pk,
                    ).order_by('questionoption__position').values('questionoption__position')[:1]
                )
            else:
                # For all other types, we just sort by treating the answer field as a string. This works fine for
                # all string-y types including dates and date-times (due to ISO 8601 format), country codes, etc
                question_subquery = Subquery(
                    QuestionAnswer.objects.filter(
                        orderposition_id=OuterRef('pk'),
                        question_id=question.pk,
                    ).order_by().values('answer')[:1]
                )

            qs = qs.annotate(
                question_answer=question_subquery,
            ).order_by(
                'question_answer'
            )

        try:
            outbuffer = render_pdf(self.event, qs, OPTIONS[form_data.get('rendering', 'one')])
        except DataError:
            logging.exception('DataError during export')
            raise ExportError(
                _('Your data could not be converted as requested. This could be caused by invalid values in your '
                  'databases, such as answers to number questions which are not a number.')
            )
        return 'badges.pdf', 'application/pdf', outbuffer.read()
