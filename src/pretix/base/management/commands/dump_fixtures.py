from __future__ import annotations

import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django_scopes import scopes_disabled


class Command(BaseCommand):
    help = """Wrapper around Django's dumpdata that disables django-scopes (pretix convenience helper).

            Examples:
            python manage.py dump_fixtures app.Model --indent 2
            python manage.py dump_fixtures app.Model --indent 2 --output fixtures.json
            """

    def create_parser(self, *args, **kwargs):
        # We want to forward *all* remaining args to Django's dumpdata, without having to re-declare its full argparse
        # surface here. Therefore, we only parse known args for this wrapper command.
        parser = super().create_parser(*args, **kwargs)
        parser.parse_args = lambda x: parser.parse_known_args(x)[0]
        return parser

    def add_arguments(self, parser):
        parser.add_argument(
            "--override",
            action="store_true",
            help="Do not disable django-scopes (advanced).",
        )

    def handle(self, *args, **options):
        # Parse unknown args from argv and forward them to dumpdata.
        parser = self.create_parser(sys.argv[0], sys.argv[1])
        unknown_args = parser.parse_known_args(sys.argv[2:])[1]

        if options.get("override"):
            return call_command("dumpdata", *unknown_args)

        with scopes_disabled():
            return call_command("dumpdata", *unknown_args)


