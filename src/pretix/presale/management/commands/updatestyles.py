#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
import hashlib

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile, File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import Event_SettingsStore, Organizer_SettingsStore
from pretix.base.settings import GlobalSettingsObject
from pretix.presale.views.widget import generate_widget_js

from ...style import regenerate_css, regenerate_organizer_css


class Command(BaseCommand):
    help = "Re-generate all custom stylesheets and scripts"

    def add_arguments(self, parser):
        parser.add_argument('--organizer', action='store', type=str)
        parser.add_argument('--event', action='store', type=str)

    @scopes_disabled()
    def handle(self, *args, **options):
        # Reset compile cache
        cache.set('sass_compile_prefix', now().isoformat())

        ostore = Organizer_SettingsStore.objects.filter(key="presale_css_file")
        if options.get('organizer'):
            ostore = ostore.filter(object__slug=options['organizer'])
        for es in ostore:
            regenerate_organizer_css.apply_async(args=(es.object_id,), kwargs={'regenerate_events': False})

        estore = Event_SettingsStore.objects.filter(key="presale_css_file").order_by('-object__date_from')
        if options.get('event'):
            estore = estore.filter(object__slug=options['event'])
        if options.get('organizer'):
            estore = estore.filter(object__organizer__slug=options['event'])
        for es in estore:
            regenerate_css.apply_async(args=(es.object_id,))

        gs = GlobalSettingsObject()
        for lc, ll in settings.LANGUAGES:
            data = generate_widget_js(lc).encode()
            checksum = hashlib.sha1(data).hexdigest()
            fname = gs.settings.get('widget_file_{}'.format(lc))
            if not fname or gs.settings.get('widget_checksum_{}'.format(lc), '') != checksum:
                newname = default_storage.save(
                    'pub/widget/widget.{}.{}.js'.format(lc, checksum),
                    ContentFile(data)
                )
                gs.settings.set('widget_file_{}'.format(lc), 'file://' + newname)
                gs.settings.set('widget_checksum_{}'.format(lc), checksum)
                cache.delete('widget_js_data_{}'.format(lc))
                if fname:
                    if isinstance(fname, File):
                        default_storage.delete(fname.name)
                    else:
                        default_storage.delete(fname)
