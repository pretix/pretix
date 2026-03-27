#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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

"""This command supersedes the Django-inbuilt runserver command.

It runs the local frontend server, if node is installed and the setting
is set.
"""
import atexit
import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import (
    Command as Parent,
)
from django.utils.autoreload import DJANGO_AUTORELOAD_ENV


class Command(Parent):
    def handle(self, *args, **options):
        # Only start Vite in the non-main process of the autoreloader
        if settings.VITE_DEV_MODE and os.environ.get(DJANGO_AUTORELOAD_ENV) != "true":
            # Start the vite server in the background
            vite_server = subprocess.Popen(
                ["npm", "run", "dev:control"],
                cwd=Path(__file__).parent.parent.parent.parent.parent
            )

            def cleanup():
                vite_server.terminate()
                try:
                    vite_server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    vite_server.kill()

            atexit.register(cleanup)

        super().handle(*args, **options)
