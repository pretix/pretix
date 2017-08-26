from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve

from pretix.base.signals import (
    register_data_exporters, register_ticket_outputs,
)
from pretix.control.signals import html_head
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


@receiver(html_head, dispatch_uid="ticketoutputpdf_html_head")
def html_head_presale(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if url.namespace == 'plugins:ticketoutputpdf':
        template = get_template('pretixplugins/ticketoutputpdf/control_head.html')
        return template.render({
            'request': request
        })
    else:
        return ""
