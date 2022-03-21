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
from django.apps import AppConfig
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from pretix import __version__ as version


class BankTransferApp(AppConfig):
    name = 'pretix.plugins.banktransfer'
    verbose_name = _("Bank transfer")

    class PretixPluginMeta:
        name = _("Bank transfer")
        author = _("the pretix team")
        category = 'PAYMENT'
        featured = True
        version = version
        description = _("Accept payments from your customers using classical wire transfer methods with your own "
                        "bank account.")

    def ready(self):
        from . import signals  # NOQA
        from . import tasks  # NOQA
        from .templatetags import commadecimal, dotdecimal  # NOQA

    @cached_property
    def compatibility_warnings(self):
        errs = []
        try:
            import chardet  # NOQA
        except ImportError:
            errs.append(_("Install the python package 'chardet' for better CSV import capabilities."))
        return errs
