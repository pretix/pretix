from functools import partial

from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import QuestionAnswer
from pretix.base.signals import (  # NOQA: legacy import
    event_copy_data, layout_text_variables, register_data_exporters,
    register_ticket_outputs,
)
from pretix.presale.style import (  # NOQA: legacy import
    get_fonts, register_fonts,
)


@receiver(register_ticket_outputs, dispatch_uid="output_pdf")
def register_ticket_outputs(sender, **kwargs):
    from .ticketoutput import PdfTicketOutput
    return PdfTicketOutput


@receiver(register_data_exporters, dispatch_uid="dataexport_pdf")
def register_data(sender, **kwargs):
    from .exporters import AllTicketsPDF
    return AllTicketsPDF


def get_answer(op, order, event, question_id):
    try:
        a = op.answers.get(question_id=question_id)
        return str(a).replace("\n", "<br/>\n")
    except QuestionAnswer.DoesNotExist:
        return ""


@receiver(layout_text_variables, dispatch_uid="pretix_ticketoutputpdf_layout_text_variables_questions")
def variables_from_questions(sender, *args, **kwargs):
    d = {}
    for q in sender.questions.all():
        d['question_{}'.format(q.pk)] = {
            'label': _('Question: {question}').format(question=q.question),
            'editor_sample': _('<Answer: {question}>').format(question=q.question),
            'evaluate': partial(get_answer, question_id=q.pk)
        }
    return d


@receiver(signal=event_copy_data, dispatch_uid="pretix_ticketoutputpdf_copy_data")
def event_copy_data_receiver(sender, other, question_map, **kwargs):
    layout = sender.settings.get('ticketoutput_pdf_layout', as_type=list)
    if not layout:
        return
    for o in layout:
        if o['type'] == 'textarea':
            if o['content'].startswith('question_'):
                o['content'] = 'question_{}'.format(question_map.get(int(o['content'][9:]), 0).pk)

    sender.settings.set('ticketoutput_pdf_layout', list(layout))
