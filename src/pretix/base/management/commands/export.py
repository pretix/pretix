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
import json
import sys

import pytz_deprecation_shim
from django.core.management.base import BaseCommand
from django.utils.timezone import override
from django_scopes import scope
from tqdm import tqdm

from pretix.base.i18n import language
from pretix.base.models import Event, Organizer
from pretix.base.signals import (
    register_data_exporters, register_multievent_data_exporters,
)


class Command(BaseCommand):
    help = "Run an exporter to get data out of pretix"

    def add_arguments(self, parser):
        parser.add_argument('organizer_slug', type=str)

        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('event_slug', nargs="?", type=str)
        group.add_argument('--all-events', action='store_true')
        group.add_argument('--event_slugs', nargs="+", type=str)

        parser.add_argument('export_provider', type=str)
        parser.add_argument('output_file', type=str)
        parser.add_argument('--parameters', action='store', type=str, help='JSON-formatted parameters')
        parser.add_argument('--locale', action='store', type=str, help='...')
        parser.add_argument('--timezone', action='store', type=str, help='...')

    def handle(self, *args, **options):
        try:
            o = Organizer.objects.get(slug=options['organizer_slug'])
        except Organizer.DoesNotExist:
            self.stderr.write(self.style.ERROR('Organizer not found.'))
            sys.exit(1)

        locale = options.get("locale", None)
        timezone = pytz_deprecation_shim.timezone(options['timezone']) if options.get('timezone') else None

        with scope(organizer=o):
            if options['event_slug']:
                try:
                    e = o.events.get(slug=options['event_slug'])
                except Event.DoesNotExist:
                    self.stderr.write(self.style.ERROR('Event not found.'))
                    sys.exit(1)
                if not locale:
                    locale = e.settings.locale
                if not timezone:
                    timezone = e.settings.timezone
                signal_result = register_data_exporters.send(e)
            else:
                e = o.events.all()
                if options['event_slugs']:
                    e = e.filter(slug__in=options['event_slugs'])
                    not_found = set(options['event_slugs']).difference(event.slug for event in e)
                    if not_found:
                        self.stderr.write(self.style.ERROR('The following events were not found: {}'.format(", ".join(not_found))))
                        sys.exit(1)
                if not e.exists():
                    self.stderr.write(self.style.ERROR('No events found.'))
                    sys.exit(1)

                if not locale:
                    locale = e.first().settings.locale
                    self.stderr.write(self.style.WARNING(
                        "Guessing locale '{}' based on event '{}'.".format(locale, e.first().slug)))
                if not timezone:
                    timezone = e.first().settings.timezone
                    self.stderr.write(self.style.WARNING(
                        "Guessing timezone '{}' based on event '{}'.".format(timezone, e.first().slug)))
                signal_result = register_multievent_data_exporters.send(o)

            pbar = tqdm(total=100)

            def report_status(val):
                pbar.update(round(val, 2) - pbar.n)

            with language(locale), override(timezone):
                for receiver, response in signal_result:
                    if not response:
                        return None
                    ex = response(e, o, report_status)
                    if ex.identifier == options['export_provider']:
                        params = json.loads(options.get('parameters') or '{}')
                        with open(options['output_file'], 'wb') as f:
                            try:
                                ex.render(form_data=params, output_file=f)
                            except TypeError:
                                self.stderr.write(self.style.WARNING(
                                    'Provider does not support direct file writing, need to buffer export in memory.'))
                                d = ex.render(form_data=params)
                                if d is None:
                                    self.stderr.write(self.style.ERROR('Empty export.'))
                                    sys.exit(2)
                                f.write(d[2])

                            sys.exit(0)
            pbar.close()

            self.stderr.write(self.style.ERROR('Export provider not found.'))
            sys.exit(1)
