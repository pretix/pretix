import logging

from pretix.base.ticketoutput import BaseTicketOutput

logger = logging.getLogger('tests.testdummy.ticketoutput')


class DummyTicketOutput(BaseTicketOutput):
    identifier = 'testdummy'
    verbose_name = 'Test dummy'
    download_button_text = 'Download test file'
    download_button_icon = 'fa-print'

    def generate(self, order):
        return 'test.txt', 'text/plain', order.identity
