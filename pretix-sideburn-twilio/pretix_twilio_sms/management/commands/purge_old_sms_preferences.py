from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_scopes import scopes_disabled

from pretix_twilio_sms.models import CustomerSmsPreference


class Command(BaseCommand):
    help = (
        "Purge CustomerSmsPreference records with last_changed older than 2 years."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=730,
            help="Age threshold in days (default: 730).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report how many records would be deleted.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]

        if days < 1:
            self.stderr.write(self.style.ERROR("--days must be at least 1"))
            return

        with scopes_disabled():
            cutoff = timezone.now() - timedelta(days=days)
            qs = CustomerSmsPreference.objects.filter(last_changed__lt=cutoff)
            count = qs.count()

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        "Dry run: {} CustomerSmsPreference record(s) older than {} day(s) "
                        "would be deleted.".format(count, days)
                    )
                )
                return

            deleted_count, _ = qs.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    "Deleted {} CustomerSmsPreference record(s) older than {} day(s).".format(
                        deleted_count, days
                    )
                )
            )
