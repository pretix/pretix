import hashlib

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from pretix.base.models import Event_SettingsStore, Organizer_SettingsStore
from pretix.base.settings import GlobalSettingsObject
from pretix.presale.views.widget import generate_widget_js

from ...style import regenerate_css, regenerate_organizer_css


class Command(BaseCommand):
    help = "Re-generate all custom stylesheets and scripts"

    def handle(self, *args, **options):
        for es in Event_SettingsStore.objects.filter(key="presale_css_file"):
            regenerate_css.apply_async(args=(es.object_id,))

        for es in Organizer_SettingsStore.objects.filter(key="presale_css_file"):
            regenerate_organizer_css.apply_async(args=(es.object_id,))

        gs = GlobalSettingsObject()
        for lc, ll in settings.LANGUAGES:
            data = generate_widget_js(lc).encode()
            checksum = hashlib.sha1(data).hexdigest()
            fname = gs.settings.get('widget_file_{}'.format(lc))
            if not fname or gs.settings.get('widget_checksum_{}'.format(lc), '') != checksum:
                newname = default_storage.save(
                    'widget/widget.{}.{}.js'.format(lc, checksum),
                    ContentFile(data)
                )
                gs.settings.set('widget_file_{}'.format(lc), 'file://' + newname)
                gs.settings.set('widget_checksum_{}'.format(lc), checksum)
                if fname:
                    default_storage.delete(fname)
