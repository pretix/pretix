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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Irmantas
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import time
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand
from django.dispatch.dispatcher import NO_RECEIVERS

from pretix.helpers.periodic import SKIPPED

from ...signals import periodic_task


class Command(BaseCommand):
    help = "Run periodic tasks"

    def add_arguments(self, parser):
        parser.add_argument('--tasks', action='store', type=str, help='Only execute the tasks with this name '
                                                                      '(dotted path, comma separation)')
        parser.add_argument('--exclude', action='store', type=str, help='Exclude the tasks with this name '
                                                                        '(dotted path, comma separation)')

    def handle(self, *args, **options):
        verbosity = int(options['verbosity'])

        if not periodic_task.receivers or periodic_task.sender_receivers_cache.get(self) is NO_RECEIVERS:
            return

        for receiver in periodic_task._live_receivers(self):
            name = f'{receiver.__module__}.{receiver.__name__}'
            if options.get('tasks'):
                if name not in options.get('tasks').split(','):
                    continue
            if options.get('exclude'):
                if name in options.get('exclude').split(','):
                    continue

            if verbosity > 1:
                self.stdout.write(f'INFO Running {name}…')
            t0 = time.time()
            try:
                r = receiver(signal=periodic_task, sender=self)
            except Exception as err:
                if isinstance(Exception, KeyboardInterrupt):
                    raise err
                if settings.SENTRY_ENABLED:
                    from sentry_sdk import capture_exception
                    capture_exception(err)
                    self.stdout.write(self.style.ERROR(f'ERROR {name}: {str(err)}\n'))
                else:
                    self.stdout.write(self.style.ERROR(f'ERROR {name}: {str(err)}\n'))
                    traceback.print_exc()
            else:
                if options.get('verbosity') > 1:
                    if r is SKIPPED:
                        self.stdout.write(self.style.SUCCESS(f'INFO Skipped {name}'))
                    else:
                        self.stdout.write(self.style.SUCCESS(f'INFO Completed {name} in {round(time.time() - t0, 3)}s'))
