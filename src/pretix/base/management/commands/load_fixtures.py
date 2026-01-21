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
from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django_scopes import scopes_disabled


class Command(BaseCommand):
    help = "Load this project's curated fixture set (with django-scopes disabled)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=("all", "base", "plugin"),
            default="all",
            help="Load only a subset of fixtures (default: all).",
        )
        parser.add_argument(
            "--ignorenonexistent",
            action="store_true",
            help="Pass --ignorenonexistent through to Django's loaddata.",
        )

    def handle(self, *args, **options):
        # Deterministic order matters due to foreign keys.
        base_fixtures = [
            "pretix/base/fixtures/organizer.json",
            "pretix/base/fixtures/customer.json",
            "pretix/base/fixtures/event.json",
            "pretix/base/fixtures/tickets.json",
            "pretix/base/fixtures/tax_and_global_settings.json",
        ]
        plugin_fixtures = [
            "pretix/plugins/ticketoutputpdf/fixtures/ticketlayout.json",
        ]

        only = options["only"]
        fixtures: list[str]
        if only == "base":
            fixtures = base_fixtures
        elif only == "plugin":
            fixtures = plugin_fixtures
        else:
            fixtures = base_fixtures + plugin_fixtures

        loaddata_opts = {}
        if options.get("ignorenonexistent"):
            loaddata_opts["ignorenonexistent"] = True

        with scopes_disabled():
            call_command("loaddata", *fixtures, **loaddata_opts)


