import os
import tempfile
from collections import OrderedDict
from zipfile import ZipFile

from django import forms
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

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
                        zipf.writestr(fname, i.file.read())
                        i.file.close()

            with open(os.path.join(d, 'tmp.zip'), 'rb') as zipf:
                return '{}_answers.zip'.format(self.event.slug), 'application/zip', zipf.read()


@receiver(register_data_exporters, dispatch_uid="exporter_answers")
def register_anwers_export(sender, **kwargs):
    return AnswerFilesExporter
