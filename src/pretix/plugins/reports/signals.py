from django.dispatch import receiver

from pretix.base.signals import register_data_exporters


@receiver(register_data_exporters, dispatch_uid="export_overview_report_pdf")
def register_report_pdf(sender, **kwargs):
    from .exporters import OverviewReport
    return OverviewReport
