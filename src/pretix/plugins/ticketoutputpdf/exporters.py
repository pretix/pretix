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
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import logging
from collections import OrderedDict
from datetime import datetime, time, timedelta
from io import BytesIO

import dateutil.parser
from django import forms
from django.core.files.base import ContentFile
from django.db import DataError, models
from django.db.models import OuterRef, Q, Subquery
from django.db.models.functions import Cast, Coalesce
from django.utils.timezone import make_aware
from django.utils.translation import gettext as _, gettext_lazy
from PyPDF2 import PdfMerger

from pretix.base.exporter import BaseExporter
from pretix.base.i18n import language
from pretix.base.models import (
    Event, Order, OrderPosition, Question, QuestionAnswer,
)
from pretix.base.settings import PERSON_NAME_SCHEMES

from ...base.services.export import ExportError
from ...helpers.templatetags.jsonfield import JSONExtract
from .ticketoutput import PdfTicketOutput

logger = logging.getLogger(__name__)


class AllTicketsPDF(BaseExporter):
    name = "alltickets"
    verbose_name = gettext_lazy("All PDF tickets in one file")
    identifier = "pdfoutput_all_tickets"

    @property
    def export_form_fields(self):
        name_scheme = PERSON_NAME_SCHEMES[self.event.settings.name_scheme] if not self.is_multievent else None
        d = OrderedDict(
            [
                ('include_pending',
                 forms.BooleanField(
                     label=_('Include pending orders'),
                     required=False
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
                     ] if name_scheme and len(name_scheme['fields']) > 1 else []) + ([
                         ('question:{}'.format(q.identifier), _('Question: {question}').format(question=q.question))
                         for q in self.event.questions.filter(type__in=(
                             # All except TYPE_FILE and future ones
                             Question.TYPE_TIME, Question.TYPE_TEXT, Question.TYPE_DATE, Question.TYPE_BOOLEAN,
                             Question.TYPE_COUNTRYCODE, Question.TYPE_DATETIME, Question.TYPE_NUMBER,
                             Question.TYPE_PHONENUMBER, Question.TYPE_STRING, Question.TYPE_CHOICE,
                             Question.TYPE_CHOICE_MULTIPLE
                         ))
                     ] if not self.is_multievent else [])
                 )),
            ]
        )

        if not self.is_multievent and not self.event.has_subevents:
            del d['date_from']
            del d['date_to']

        return d

    def render(self, form_data):
        merger = PdfMerger()
        qs = OrderPosition.objects.filter(
            order__event__in=self.events
        ).prefetch_related(
            'answers', 'answers__question'
        ).select_related('order', 'item', 'variation', 'addon_to')

        if form_data.get('include_pending'):
            qs = qs.filter(order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING])
        else:
            qs = qs.filter(order__status__in=[Order.STATUS_PAID])

        if form_data.get('date_from'):
            dt = make_aware(datetime.combine(
                dateutil.parser.parse(form_data['date_from']).date(),
                time(hour=0, minute=0, second=0)
            ), self.timezone)
            qs = qs.filter(Q(subevent__date_from__gte=dt) | Q(subevent__isnull=True, order__event__date_from__gte=dt))

        if form_data.get('date_to'):
            dt = make_aware(datetime.combine(
                dateutil.parser.parse(form_data['date_to']).date() + timedelta(days=1),
                time(hour=0, minute=0, second=0)
            ), self.timezone)
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
                resolved_name=Coalesce('attendee_name_parts', 'addon_to__attendee_name_parts', 'order__invoice_address__name_parts')
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

        o = PdfTicketOutput(Event.objects.none())
        try:
            for op in qs:
                if not op.generate_ticket:
                    continue

                if op.order.event != o.event:
                    o = PdfTicketOutput(op.event)

                with language(op.order.locale, o.event.settings.region):
                    layout = o.layout_map.get(
                        (op.item_id, op.order.sales_channel),
                        o.layout_map.get(
                            (op.item_id, 'web'),
                            o.default_layout
                        )
                    )
                    outbuffer = o._draw_page(layout, op, op.order)
                    merger.append(ContentFile(outbuffer.read()))

            outbuffer = BytesIO()
            merger.write(outbuffer)
            merger.close()
            outbuffer.seek(0)
        except DataError:
            logging.exception('DataError during export')
            raise ExportError(
                _('Your data could not be converted as requested. This could be caused by invalid values in your '
                  'databases, such as answers to number questions which are not a number.')
            )

        if self.is_multievent:
            return '{}_tickets.pdf'.format(self.events.first().organizer.slug), 'application/pdf', outbuffer.read()
        else:
            return '{}_tickets.pdf'.format(self.event.slug), 'application/pdf', outbuffer.read()
