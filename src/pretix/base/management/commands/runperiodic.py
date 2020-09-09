import time
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand
from django.dispatch.dispatcher import NO_RECEIVERS

from pretix.helpers.periodic import SKIPPED

from ...signals import periodic_task


class Command(BaseCommand):
    help = "Run periodic tasks"

    def handle(self, *args, **options):
        verbosity = int(options['verbosity'])

        if not periodic_task.receivers or periodic_task.sender_receivers_cache.get(self) is NO_RECEIVERS:
            return

        for receiver in periodic_task._live_receivers(self):
            if verbosity > 1:
                self.stdout.write(f'Running {receiver.__module__}.{receiver.__name__}…')
            t0 = time.time()
            try:
                r = receiver(signal=periodic_task, sender=self)
            except Exception as err:
                if isinstance(Exception, KeyboardInterrupt):
                    raise err
                if settings.SENTRY_ENABLED:
                    from sentry_sdk import capture_exception
                    capture_exception(err)
                    self.stdout.write(self.style.ERROR(f'FAIL: {str(err)}\n'))
                else:
                    self.stdout.write(self.style.ERROR(f'FAIL: {str(err)}\n'))
                    traceback.print_exc()
            else:
                if options.get('verbosity') > 1:
                    if r is SKIPPED:
                        self.stdout.write(self.style.SUCCESS(f'Skipped {receiver.__module__}.{receiver.__name__}'))
                    else:
                        self.stdout.write(self.style.SUCCESS(f'Completed {receiver.__module__}.{receiver.__name__} in {round(time.time() - t0, 3)}s'))
