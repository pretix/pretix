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

import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django_scopes import scopes_disabled


class Command(BaseCommand):
    help = "Wrapper around Django's dumpdata that disables django-scopes (pretix convenience helper)."

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


