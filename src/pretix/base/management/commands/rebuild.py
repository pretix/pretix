from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Rebuild static files and language files"

    def handle(self, *args, **options):
        call_command('compilemessages', verbosity=1, interactive=False)
        call_command('compilejsi18n', verbosity=1, interactive=False)
        call_command('collectstatic', verbosity=1, interactive=False)
        call_command('compress', verbosity=1, interactive=False)
