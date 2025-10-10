#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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

import os
import tempfile
from collections import OrderedDict
from zipfile import ZipFile

from django import forms
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from pretix.base.models import QuestionAnswer

from ...control.forms.widgets import Select2
from ..exporter import BaseExporter
from ..signals import register_data_exporters


class AnswerFilesExporter(BaseExporter):
    identifier = 'answerfiles'
    verbose_name = _('Question answer file uploads')
    category = pgettext_lazy('export_category', 'Order data')
    description = _('Download a ZIP file including all files that have been uploaded by your customers while creating '
                    'an order.')

    @property
    def export_form_fields(self):
        d = OrderedDict(
            [
                ('questions',
                 forms.ModelMultipleChoiceField(
                     queryset=self.event.questions.filter(type='F'),
                     label=_('Questions'),
                     widget=forms.CheckboxSelectMultiple(
                         attrs={'class': 'scrolling-multiple-choice'}
                     ),
                     required=False
                 )),
            ]
        )
        if self.event.has_subevents:
            d['subevent'] = forms.ModelChoiceField(
                label=pgettext_lazy('subevent', 'Date'),
                queryset=self.event.subevents.all(),
                required=False,
                empty_label=pgettext_lazy('subevent', 'All dates')
            )
            d['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            d['subevent'].widget.choices = d['subevent'].choices
        return d

    def render(self, form_data: dict):
        qs = QuestionAnswer.objects.filter(
            orderposition__order__event=self.event,
        ).select_related('orderposition', 'orderposition__order', 'question')
        if form_data.get('subevent'):
            qs = qs.filter(orderposition__subevent=form_data.get('subevent'))
        if form_data.get('questions'):
            qs = qs.filter(question__in=form_data['questions'])
        with tempfile.TemporaryDirectory() as d:
            any = False
            with ZipFile(os.path.join(d, 'tmp.zip'), 'w') as zipf:
                for i in qs:
                    if i.file:
                        i.file.open('rb')
                        fname = '{}-{}-{}-q{}-{}'.format(
                            self.event.slug.upper(),
                            i.orderposition.order.code,
                            i.orderposition.positionid,
                            i.question.pk,
                            os.path.basename(i.file.name).split('.', 1)[1]
                        )
                        any = True
                        zipf.writestr(fname, i.file.read())
                        i.file.close()

            if not any:
                return None
            with open(os.path.join(d, 'tmp.zip'), 'rb') as zipf:
                return '{}_answers.zip'.format(self.event.slug), 'application/zip', zipf.read()


@receiver(register_data_exporters, dispatch_uid="exporter_answers")
def register_anwers_export(sender, **kwargs):
    return AnswerFilesExporter
