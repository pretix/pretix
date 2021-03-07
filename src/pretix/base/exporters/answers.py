#
# This file is part of pretix Community.
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
# ADDITIONAL TERMS: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are applicable
# granting you additional permissions and placing additional restrictions on your usage of this software. Please refer
# to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive this file, see
# <https://pretix.eu/about/en/license>.
#
import os
import tempfile
from collections import OrderedDict
from zipfile import ZipFile

from django import forms
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from pretix.base.models import QuestionAnswer

from ..exporter import BaseExporter
from ..signals import register_data_exporters


class AnswerFilesExporter(BaseExporter):
    identifier = 'answerfiles'
    verbose_name = _('Answers to file upload questions')

    @property
    def export_form_fields(self):
        return OrderedDict(
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

    def render(self, form_data: dict):
        qs = QuestionAnswer.objects.filter(
            orderposition__order__event=self.event,
        ).select_related('orderposition', 'orderposition__order', 'question')
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
