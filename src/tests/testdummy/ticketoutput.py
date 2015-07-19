import logging

from django.http import HttpResponse

from pretix.base.ticketoutput import BaseTicketOutput

logger = logging.getLogger('tests.testdummy.ticketoutput')


class DummyTicketOutput(BaseTicketOutput):
    identifier = 'testdummy'
    verbose_name = 'Test dummy'
    download_button_text = 'Download test file'
    download_button_icon = 'fa-print'

    def generate(self, request, order):
        response = HttpResponse(order.identity, content_type='text/plain')
        return response
