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
import logging
import sys

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django_scopes import scope, scopes_disabled


class Command(BaseCommand):
    def create_parser(self, *args, **kwargs):
        parser = super().create_parser(*args, **kwargs)
        parser.parse_args = lambda x: parser.parse_known_args(x)[0]
        return parser

    def add_arguments(self, parser):
        parser.add_argument(
            '--print-sql',
            action='store_true',
            help='Print all SQL queries.',
        )

    def handle(self, *args, **options):
        try:
            from django_extensions.management.commands import shell_plus  # noqa
            cmd = 'shell_plus'
        except ImportError:
            cmd = 'shell'
            del options['skip_checks']
            del options['print_sql']

        if options.get('print_sql'):
            connection.force_debug_cursor = True
            logger = logging.getLogger("django.db.backends")
            logger.setLevel(logging.DEBUG)

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
