from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from ...signals import periodic_task


class Command(BaseCommand):
    help = "Run periodic tasks"

    def handle(self, *args, **options):
        for recv, resp in periodic_task.send_robust(self):
            if isinstance(resp, Exception):
                if settings.SENTRY_ENABLED:
                    from sentry_sdk import capture_exception
                    capture_exception(resp)
                else:
                    raise resp

        call_command('clearsessions')
