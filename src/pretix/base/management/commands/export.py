import json
import sys

from django.core.management.base import BaseCommand
from django.utils.timezone import override
from django_scopes import scope
from tqdm import tqdm

from pretix.base.i18n import language
from pretix.base.models import Event, Organizer
from pretix.base.signals import register_data_exporters


class Command(BaseCommand):
    help = "Run an exporter to get data out of pretix"

    def add_arguments(self, parser):
        parser.add_argument('organizer_slug', nargs=1, type=str)
        parser.add_argument('event_slug', nargs=1, type=str)
        parser.add_argument('export_provider', nargs=1, type=str)
        parser.add_argument('output_file', nargs=1, type=str)
        parser.add_argument('--parameters', action='store', type=str, help='JSON-formatted parameters')

    def handle(self, *args, **options):
        try:
            o = Organizer.objects.get(slug=options['organizer_slug'][0])
        except Organizer.DoesNotExist:
            self.stderr.write(self.style.ERROR('Organizer not found.'))
            sys.exit(1)

        with scope(organizer=o):
            try:
                e = o.events.get(slug=options['event_slug'][0])
            except Event.DoesNotExist:
                self.stderr.write(self.style.ERROR('Event not found.'))
                sys.exit(1)

            pbar = tqdm(total=100)

            def report_status(val):
                pbar.update(round(val, 2) - pbar.n)

            with language(e.settings.locale), override(e.settings.timezone):
                responses = register_data_exporters.send(e)
                for receiver, response in responses:
                    ex = response(e, report_status)
                    if ex.identifier == options['export_provider'][0]:
                        params = json.loads(options.get('parameters') or '{}')
                        with open(options['output_file'][0], 'wb') as f:
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
