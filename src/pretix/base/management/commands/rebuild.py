from django.core.management import call_command
from django.core.management.base import BaseCommand

from pretix.base.settings import GlobalSettingsObject


class Command(BaseCommand):
    help = "Rebuild static files and language files"

    def handle(self, *args, **options):
        call_command('compilemessages', verbosity=1)
        call_command('compilejsi18n', verbosity=1)
        call_command('collectstatic', verbosity=1, interactive=False)
        call_command('compress', verbosity=1)
        try:
            gs = GlobalSettingsObject()
            del gs.settings.update_check_last
            del gs.settings.update_check_result
            del gs.settings.update_check_result_warning
        except:
            # Fails when this is executed without a valid database configuration.
            # We don't care.
            pass
