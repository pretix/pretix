from django.core.management import call_command
from django.core.management.base import BaseCommand

from ...signals import periodic_task


class Command(BaseCommand):
    help = "Run periodic tasks"

    def handle(self, *args, **options):
        periodic_task.send(self)
        call_command('clearsessions')
