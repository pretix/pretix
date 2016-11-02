import logging

from pretix.base.ticketoutput import BaseTicketOutput

logger = logging.getLogger('tests.testdummy.ticketoutput')


class DummyTicketOutput(BaseTicketOutput):
    identifier = 'testdummy'
    verbose_name = 'Test dummy'
    download_button_text = 'Download test file'

    def generate(self, op):
        return 'test.txt', 'text/plain', str(op.order.id)
