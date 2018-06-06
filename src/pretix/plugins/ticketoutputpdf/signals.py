import copy
import json
from functools import partial

from django.dispatch import receiver
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import QuestionAnswer
from pretix.base.signals import (  # NOQA: legacy import
    event_copy_data, item_copy_data, layout_text_variables, logentry_display,
    logentry_object_link, register_data_exporters, register_ticket_outputs,
)
from pretix.control.signals import item_forms
from pretix.plugins.ticketoutputpdf.forms import TicketLayoutItemForm
from pretix.plugins.ticketoutputpdf.models import (
    TicketLayout, TicketLayoutItem,
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


@receiver(item_forms, dispatch_uid="pretix_ticketoutputpdf_item_forms")
def control_item_forms(sender, request, item, **kwargs):
    try:
        inst = TicketLayoutItem.objects.get(item=item)
    except TicketLayoutItem.DoesNotExist:
        inst = TicketLayoutItem(item=item)
    return TicketLayoutItemForm(
        instance=inst,
        event=sender,
        data=(request.POST if request.method == "POST" else None),
        prefix="ticketlayoutitem"
    )


@receiver(item_copy_data, dispatch_uid="pretix_ticketoutputpdf_item_copy")
def copy_item(sender, source, target, **kwargs):
    try:
        inst = TicketLayoutItem.objects.get(item=source)
        TicketLayoutItem.objects.create(item=target, layout=inst.layout)
    except TicketLayoutItem.DoesNotExist:
        pass


@receiver(signal=event_copy_data, dispatch_uid="pretix_ticketoutputpdf_copy_data")
def pdf_event_copy_data_receiver(sender, other, item_map, question_map, **kwargs):
    if sender.ticket_layouts.exists():  # idempotency
        return
    layout_map = {}
    for bl in other.ticket_layouts.all():
        oldid = bl.pk
        bl = copy.copy(bl)
        bl.pk = None
        bl.event = sender

        layout = json.loads(bl.layout)
        for o in layout:
            if o['type'] == 'textarea':
                if o['content'].startswith('question_'):
                    o['content'] = 'question_{}'.format(question_map.get(int(o['content'][9:]), 0).pk)
        bl.layout = json.dumps(layout)

        bl.save()

        if bl.background and bl.background.name:
            bl.background.save('background.pdf', bl.background)

        layout_map[oldid] = bl

    for bi in TicketLayoutItem.objects.filter(item__event=other):
        TicketLayoutItem.objects.create(item=item_map.get(bi.item_id), layout=layout_map.get(bi.layout_id))
    return layout_map


@receiver(signal=logentry_display, dispatch_uid="pretix_ticketoutputpdf_logentry_display")
def pdf_logentry_display(sender, logentry, **kwargs):
    if not logentry.action_type.startswith('pretix.plugins.ticketoutputpdf'):
        return

    plains = {
        'pretix.plugins.ticketoutputpdf.layout.added': _('Ticket layout created.'),
        'pretix.plugins.ticketoutputpdf.layout.deleted': _('Ticket layout deleted.'),
        'pretix.plugins.ticketoutputpdf.layout.changed': _('Ticket layout changed.'),
    }

    if logentry.action_type in plains:
        return plains[logentry.action_type]


@receiver(signal=logentry_object_link, dispatch_uid="pretix_ticketoutputpdf_logentry_object_link")
def pdf_logentry_object_link(sender, logentry, **kwargs):
    if not logentry.action_type.startswith('pretix.plugins.ticketoutputpdf.layout') or not isinstance(
            logentry.content_object, TicketLayout):
        return

    a_text = _('Ticket layout {val}')
    a_map = {
        'href': reverse('plugins:ticketoutputpdf:edit', kwargs={
            'event': sender.slug,
            'organizer': sender.organizer.slug,
            'layout': logentry.content_object.id
        }),
        'val': escape(logentry.content_object.name),
    }
    a_map['val'] = '<a href="{href}">{val}</a>'.format_map(a_map)
    return a_text.format_map(a_map)
