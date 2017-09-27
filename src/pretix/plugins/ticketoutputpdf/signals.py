from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve

from pretix.base.signals import (
    EventPluginSignal, register_data_exporters, register_ticket_outputs,
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
    if url.namespace == 'plugins:ticketoutputpdf' and getattr(request, 'organizer', None):
        template = get_template('pretixplugins/ticketoutputpdf/control_head.html')
        return template.render({
            'request': request
        })
    else:
        return ""


layout_text_variables = EventPluginSignal()
"""
This signal is sent out to collect variables that can be used to display text in PDF ticket layouts.
Receivers are expected to return a dictionary with globally unique identifiers as keys and more
dictionaries as values that contain keys like in the following example::

    return {
        "product": {
            "label": _("Product name"),
            "editor_sample": _("Sample product"),
            "evaluate": lambda orderposition, order, event: str(orderposition.item)
        }
    }

The evaluate member will be called with the order position, order and event as arguments. The event might
also be a subevent, if applicable.
"""
