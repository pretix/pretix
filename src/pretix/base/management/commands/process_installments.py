from django.core.management.base import BaseCommand

from pretix.base.services.installments import (
    process_due_installments, process_expired_plans,
    send_grace_period_warnings, send_installment_reminders,
)


class Command(BaseCommand):
    help = "Process due installment payments"

    def handle(self, *args, **options):
        process_due_installments()
        process_expired_plans()
        send_installment_reminders()
        send_grace_period_warnings()
