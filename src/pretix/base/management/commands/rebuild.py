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
from django.core.management import call_command
from django.core.management.base import BaseCommand

from pretix.base.settings import GlobalSettingsObject


class Command(BaseCommand):
    help = "Rebuild static files and language files"

    def handle(self, *args, **options):
        call_command('compilemessages', verbosity=1)
        call_command('compilejsi18n', verbosity=1)
        call_command('collectstatic', verbosity=1, interactive=False)
        call_command('compress', verbosity=1)
        try:
            gs = GlobalSettingsObject()
            del gs.settings.update_check_last
            del gs.settings.update_check_result
            del gs.settings.update_check_result_warning
        except:
            # Fails when this is executed without a valid database configuration.
            # We don't care.
            pass
