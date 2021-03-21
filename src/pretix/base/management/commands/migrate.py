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
"""
Django tries to be helpful by suggesting to run "makemigrations" in red font on every "migrate"
run when there are things we have no migrations for. Usually, this is intended, and running
"makemigrations" can really screw up the environment of a user, so we want to prevent novice
users from doing that by going really dirty and filtering it from the output.
"""
import sys

from django.core.management.base import OutputWrapper
from django.core.management.commands.migrate import Command as Parent


class OutputFilter(OutputWrapper):
    banlist = (
        "Your models have changes that are not yet reflected",
        "Run 'manage.py makemigrations' to make new "
    )

    def write(self, msg, style_func=None, ending=None):
        if any(b in msg for b in self.banlist):
            return
        super().write(msg, style_func, ending)


class Command(Parent):
    def __init__(self, stdout=None, stderr=None, no_color=False, force_color=False):
        super().__init__(stdout, stderr, no_color, force_color)
        self.stdout = OutputFilter(stdout or sys.stdout)
