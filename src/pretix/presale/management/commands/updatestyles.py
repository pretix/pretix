from django.core.management.base import BaseCommand

from pretix.base.models import Event_SettingsStore, Organizer_SettingsStore

from ...style import regenerate_css, regenerate_organizer_css


class Command(BaseCommand):
    help = "Re-generate all custom stylesheets"

    def handle(self, *args, **options):
        for es in Event_SettingsStore.objects.filter(key="presale_css_file"):
            regenerate_css.apply_async(args=(es.object_id,))
        for es in Organizer_SettingsStore.objects.filter(key="presale_css_file"):
            regenerate_organizer_css.apply_async(args=(es.object_id,))
