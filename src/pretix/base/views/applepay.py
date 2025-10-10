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
from django.http import Http404, HttpResponse

from pretix.base.settings import GlobalSettingsObject


def association(request, *args, **kwargs):
    # This is a crutch to enable event- or organizer-level overrides for the default
    # ApplePay MerchantID domain validation/association file.
    # We do not provide any FormFields for this on purpose!
    #
    # Please refer to https://github.com/pretix/pretix/pull/3611 to get updates on
    # the upcoming and official way to temporarily override the association-file,
    # which will make sure that there are no conflicting requests at the same time.
    #
    # Should you opt to manually inject a different association-file into an organizer
    # or event settings store, we do recommend to remove the setting once you're
    # done and the domain has been validated.
    #
    # If you do not need Stripe's default domain association credential and would
    # rather serve a different default credential, you can do so through the
    # Global Settings editor.
    if hasattr(request, 'event'):
        settings = request.event.settings
    elif hasattr(request, 'organizer'):
        settings = request.organizer.settings
    else:
        settings = GlobalSettingsObject().settings

    if not settings.get('apple_domain_association', None):
        raise Http404('')
    else:
        return HttpResponse(settings.get('apple_domain_association'))
