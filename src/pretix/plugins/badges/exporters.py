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
import os
import subprocess
import tempfile
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from typing import BinaryIO, List, Optional, Tuple

import dateutil.parser
from django import forms
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import DataError, models
from django.db.models import Case, Exists, OuterRef, Q, Subquery, When
from django.db.models.functions import Cast, Coalesce
from django.utils.timezone import make_aware
from django.utils.translation import gettext as _, gettext_lazy, pgettext_lazy
from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.lib import pagesizes
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from pretix.base.exporter import BaseExporter
from pretix.base.i18n import language
from pretix.base.models import (
    Event, Order, OrderPosition, Question, QuestionAnswer,
)
from pretix.base.pdf import Renderer, merge_background
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
    ('lyreco_70x36', {
        'name': 'Lyreco 70 x 36 mm (143.344)',
        'cols': 3,
        'rows': 8,
        'margins': [4.5 * mm, 0 * mm, 4.5 * mm, 0 * mm],
        'offsets': [70 * mm, 36 * mm],
        'pagesize': pagesizes.A4,
    }),
])


def _chunks(lst, n):
    """
    Yield successive n-sized chunks from lst.
    """
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _render_nup_page(nup_pdf: PdfWriter, input_pages: PageObject, opt: dict) -> PageObject:
    """
    Render the `Page` objects in `input_pages` onto one page of `nup_pdf` using the options given in `opt` and
    return the newly created page.
    """
    badges_per_page = opt['cols'] * opt['rows']
    nup_page = nup_pdf.add_blank_page(
        width=Decimal('%.5f' % (opt['pagesize'][0])),
        height=Decimal('%.5f' % (opt['pagesize'][1])),
    )
    for i, page in enumerate(input_pages):
        di = i % badges_per_page
        tx = opt['margins'][3] + (di % opt['cols']) * opt['offsets'][0]
        ty = opt['margins'][2] + (opt['rows'] - 1 - (di // opt['cols'])) * opt['offsets'][1]
        page.add_transformation(Transformation().translate(tx, ty))
        page.mediabox = RectangleObject((
            Decimal('%.5f' % (page.mediabox.left.as_numeric() + tx)),
            Decimal('%.5f' % (page.mediabox.bottom.as_numeric() + ty)),
            Decimal('%.5f' % (page.mediabox.right.as_numeric() + tx)),
            Decimal('%.5f' % (page.mediabox.top.as_numeric() + ty))
        ))
        page.trimbox = page.mediabox
        nup_page.merge_page(page)
    return nup_page


def _merge_pages(file_paths: List[str], output_file: BinaryIO):
    """
    Merge all pages from the PDF files named `file_paths` into the `output_file`.
    """
    if settings.PDFTK:
        subprocess.run([
            settings.PDFTK,
            *file_paths,
            'cat',
            'output',
            '-',
            'compress'
        ], check=True, stdout=output_file)
    else:
        merger = PdfWriter()
        merger.add_metadata({
            '/Title': 'Badges',
            '/Creator': 'pretix',
        })
        # append all temp-PDFs
        for pdf in file_paths:
            merger.append(pdf)

        # write merged PDFs to buffer
        merger.write(output_file)


def _render_nup(input_files: List[str], num_pages: int, output_file: BytesIO, opt: dict):
    """
    Render the pages from the PDF files listed in `input_files` (file names) with a total number of `num_pages` pages
    into one file written to `output_file` using the -nup options given in `opt`.
    """
    badges_per_page = opt['cols'] * opt['rows']
    max_nup_pages = 20  # chunk size to prevent working with huge files
    nup_pdf_files = []
    temp_dir = None
    if num_pages > badges_per_page * max_nup_pages:
        # to reduce memory consumption with lots of badges
        # we try to use temporary PDF-files with up to
        # max_nup_pages pages
        # If temp-files fail, we try to merge in-memory anyways
        try:
            temp_dir = tempfile.TemporaryDirectory()
        except IOError:
            pass

    try:
        badges_pdf = PdfReader(input_files.pop())
        offset = 0
        for i, chunk_indices in enumerate(_chunks(range(num_pages), badges_per_page * max_nup_pages)):
            chunk = []
            for j in chunk_indices:
                # We need to dynamically switch to the next input file as we don't know how many pages each input
                # file has beforehand
                if j - offset >= len(badges_pdf.pages):
                    offset += len(badges_pdf.pages)
                    badges_pdf = PdfReader(input_files.pop())
                chunk.append(badges_pdf.pages[j - offset])
            # Reset some internal state from pypdf. This will make it a little slower, but will prevent us from
            # running out of memory if we process a really large file.
            badges_pdf.flattened_pages = None

            nup_pdf = PdfWriter()
            nup_pdf.add_metadata({
                '/Title': 'Badges',
                '/Creator': 'pretix',
            })

            for page_chunk in _chunks(chunk, badges_per_page):
                _render_nup_page(nup_pdf, page_chunk, opt)

            if temp_dir:
                file_path = os.path.join(temp_dir.name, 'badges-%d.pdf' % i)
                nup_pdf.write(file_path)
                nup_pdf_files.append(file_path)
            else:
                # everything fitted into one nup_pdf -- we can save some work
                nup_pdf.write(output_file)
                return

        del badges_pdf  # free up memory

        file_paths = [os.path.join(temp_dir.name, fp) for fp in nup_pdf_files]
        _merge_pages(file_paths, output_file)
    finally:
        if temp_dir:
            try:
                temp_dir.cleanup()
            except IOError:
                pass


def _render_badges(event: Event, positions: List[OrderPosition], opt: dict) -> Tuple[PdfWriter, PdfWriter, int]:
    """
    Render the badges for the given order positions into two different files, one with the foregrounds and one with
    the backgrounds.
    """
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

    fg_pdf = PdfWriter()
    fg_pdf.add_metadata({
        '/Title': 'Badges',
        '/Creator': 'pretix',
    })
    bg_pdf = PdfWriter()
    num_pages = 0
    for op, renderer in op_renderers:
        buffer = BytesIO()
        page = canvas.Canvas(buffer, pagesize=pagesizes.A4)
        with language(op.order.locale, op.order.event.settings.region):
            renderer.draw_page(page, op.order, op)

        if opt['pagesize']:
            page.setPageSize(opt['pagesize'])
        page.save()
        # to reduce disk-IO render backgrounds in own PDF and merge later
        fg_pdf.append(buffer)
        new_num_pages = len(fg_pdf.pages)
        for i in range(new_num_pages - num_pages):
            bg_pdf.add_page(renderer.bg_pdf.pages[i])
        num_pages = new_num_pages

    return fg_pdf, bg_pdf, num_pages


def render_pdf(event, positions, opt, output_file):
    Renderer._register_fonts()
    badges_per_page = opt['cols'] * opt['rows']

    if badges_per_page == 1:
        fg_pdf, bg_pdf, _ = _render_badges(event, positions, opt)
        merge_background(
            fg_pdf,
            bg_pdf,
            output_file,
            compress=True,
        )
    else:
        # place n-up badges/pages per page
        with tempfile.TemporaryDirectory() as tmp_dir:
            page_pdfs = []
            total_num_pages = 0
            for position_chunk in _chunks(positions, 200):
                # We first render the foreground and background of every individual badge and merge them, but we do
                # so in chunks, since the n-up code is slower if it has to deal with huge PDFs. It doesn't matter
                # that not every position has the same number of pages, as the n-up code can deal with that
                fg_pdf, bg_pdf, num_pages = _render_badges(event, position_chunk, opt)
                out_pdf_name = os.path.join(tmp_dir, f'chunk-{len(page_pdfs)}.pdf')
                with open(out_pdf_name, 'wb') as out_pdf:
                    merge_background(
                        fg_pdf,
                        bg_pdf,
                        out_pdf,
                        compress=False,
                    )
                page_pdfs.append(out_pdf_name)
                total_num_pages += num_pages
                del fg_pdf, bg_pdf  # free up memory

            # Actually render a n-up file
            return _render_nup(page_pdfs, total_num_pages, output_file, opt)


class BadgeExporter(BaseExporter):
    identifier = "badges"
    verbose_name = _("Attendee badges")
    category = pgettext_lazy('export_category', 'PDF collections')
    description = gettext_lazy('Download all attendee badges as one large PDF for printing.')
    featured = True

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

    def render(self, form_data: dict, output_file=None) -> Tuple[str, str, Optional[bytes]]:
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
            qs = qs.filter(Q(order__status=Order.STATUS_PAID) | Q(order__status=Order.STATUS_PENDING, order__valid_if_pending=True))

        if form_data.get('date_from'):
            if not isinstance(form_data.get('date_from'), date):
                form_data['date_from'] = dateutil.parser.parse(form_data['date_from']).date()
            df = make_aware(datetime.combine(
                form_data['date_from'],
                time(hour=0, minute=0, second=0)
            ), self.event.timezone)
            qs = qs.filter(Q(subevent__date_from__gte=df) | Q(subevent__isnull=True, order__event__date_from__gte=df))

        if form_data.get('date_to'):
            if not isinstance(form_data.get('date_to'), date):
                form_data['date_to'] = dateutil.parser.parse(form_data['date_to']).date()
            dt = make_aware(datetime.combine(
                form_data['date_to'] + timedelta(days=1),
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
                resolved_name=Case(
                    When(attendee_name_cached__ne='', then='attendee_name_parts'),
                    When(addon_to__attendee_name_cached__isnull=False, addon_to__attendee_name_cached__ne='',
                         then='addon_to__attendee_name_parts'),
                    default='order__invoice_address__name_parts',
                )
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
            if output_file:
                render_pdf(self.event, qs, OPTIONS[form_data.get('rendering', 'one')], output_file=output_file)
                return 'badges.pdf', 'application/pdf', None
            else:
                with tempfile.NamedTemporaryFile(delete=True) as tmpfile:
                    render_pdf(self.event, qs, OPTIONS[form_data.get('rendering', 'one')], output_file=tmpfile)
                    tmpfile.seek(0)
                    return 'badges.pdf', 'application/pdf', tmpfile.read()
        except DataError:
            logging.exception('DataError during export')
            raise ExportError(
                _('Your data could not be converted as requested. This could be caused by invalid values in your '
                  'databases, such as answers to number questions which are not a number.')
            )
