import sys

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django_scopes import scope, scopes_disabled


class Command(BaseCommand):
    def create_parser(self, *args, **kwargs):
        parser = super().create_parser(*args, **kwargs)
        parser.parse_args = lambda x: parser.parse_known_args(x)[0]
        return parser

    def handle(self, *args, **options):
        try:
            from django_extensions.management.commands import shell_plus  # noqa
            cmd = 'shell_plus'
        except ImportError:
            cmd = 'shell'
            del options['skip_checks']

        parser = self.create_parser(sys.argv[0], sys.argv[1])
        flags = parser.parse_known_args(sys.argv[2:])[1]
        if "--override" in flags:
            with scopes_disabled():
                return call_command(cmd, *args, **options)

        lookups = {}
        for flag in flags:
            lookup, value = flag.lstrip("-").split("=")
            lookup = lookup.split("__", maxsplit=1)
            lookups[lookup[0]] = {
                lookup[1] if len(lookup) > 1 else "pk": value
            }
        models = {
            model_name.split(".")[-1]: model_class
            for app_name, app_content in apps.all_models.items()
            for (model_name, model_class) in app_content.items()
        }
        scope_options = {
            app_name: models[app_name].objects.get(**app_value)
            for app_name, app_value in lookups.items()
        }
        with scope(**scope_options):
            return call_command(cmd, *args, **options)
