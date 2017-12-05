from django.dispatch import receiver

from pretix.base.signals import register_data_exporters


@receiver(register_data_exporters, dispatch_uid="export_checkinlist_csv")
def register_csv(sender, **kwargs):
    from .exporters import CSVCheckinList
    return CSVCheckinList


@receiver(register_data_exporters, dispatch_uid="export_checkinlist_pdf")
def register_pdf(sender, **kwargs):
    from .exporters import PDFCheckinList
    return PDFCheckinList
