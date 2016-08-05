import os
import tempfile
from zipfile import ZipFile

from django.dispatch import receiver
from django.utils.translation import ugettext as _

from ..exporter import BaseExporter
from ..models import Invoice
from ..signals import register_data_exporters


class InvoiceExporter(BaseExporter):
    identifier = 'invoices'
    verbose_name = _('All invoices')

    def render(self, form_data: dict):
        with tempfile.TemporaryDirectory() as d:
            with ZipFile(os.path.join(d, 'tmp.zip'), 'w') as zipf:
                for i in self.event.invoices.all():
                    i.file.open('r')
                    zipf.writestr('{}.pdf'.format(i.number), i.file.read())
                    i.file.close()

            with open(os.path.join(d, 'tmp.zip'), 'rb') as zipf:
                return 'invoices.zip', 'application/zip', zipf.read()


@receiver(register_data_exporters, dispatch_uid="exporter_invoices")
def register_invoice_export(sender, **kwargs):
    return InvoiceExporter
