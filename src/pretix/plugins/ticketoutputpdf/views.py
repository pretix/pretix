import logging

from django.templatetags.static import static
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import (
    CachedCombinedTicket, CachedTicket, OrderPosition,
)
from pretix.control.views.pdf import BaseEditorView
from pretix.plugins.ticketoutputpdf.ticketoutput import PdfTicketOutput

logger = logging.getLogger(__name__)


class EditorView(BaseEditorView):
    title = _('Default ticket layout')

    def get_output(self, *args, **kwargs):
        return PdfTicketOutput(self.request.event, *args, **kwargs)

    def save_layout(self):
        super().save_layout()
        CachedTicket.objects.filter(
            order_position__order__event=self.request.event, provider='pdf'
        ).delete()
        CachedCombinedTicket.objects.filter(
            order__event=self.request.event, provider='pdf'
        ).delete()

    def get_layout_settings_key(self):
        return 'ticketoutput_pdf_layout'

    def get_background_settings_key(self):
        return 'ticketoutput_pdf_background'

    def get_default_background(self):
        return static('pretixpresale/pdf/ticket_default_a4.pdf')

    def generate(self, p: OrderPosition, override_layout=None, override_background=None):
        prov = self.get_output(
            override_layout=override_layout,
            override_background=override_background
        )
        fname, mimet, data = prov.generate(p)
        return fname, mimet, data

    def get_current_layout(self):
        prov = self.get_output()
        return (
            self.request.event.settings.get(self.get_layout_settings_key(), as_type=list)
            or prov._default_layout()
        )
