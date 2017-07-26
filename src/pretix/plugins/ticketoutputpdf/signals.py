from django.dispatch import Signal, receiver
from django.template.loader import get_template
from django.urls import resolve

from pretix.base.signals import (
    register_data_exporters, register_ticket_outputs,
)
from pretix.control.signals import html_head


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


register_fonts = Signal()
"""
Return a dictionaries of the following structure. Paths should be relative to static root.

{
    "font name": {
        "regular": {
            "truetype": "….ttf",
            "woff": "…",
            "woff2": "…"
        },
        "bold": {
            ...
        },
        "italic": {
            ...
        },
        "bolditalic": {
            ...
        }
    }
}
"""


def get_fonts():
    f = {}
    for recv, value in register_fonts.send(0):
        f.update(value)
    return f
