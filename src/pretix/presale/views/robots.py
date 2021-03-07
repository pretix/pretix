#
# This file is part of pretix Community.
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
# ADDITIONAL TERMS: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are applicable
# granting you additional permissions and placing additional restrictions on your usage of this software. Please refer
# to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive this file, see
# <https://pretix.eu/about/en/license>.
#
from django.http import HttpResponse
from django.views.decorators.cache import cache_page


class NoSearchIndexViewMixin:
    def dispatch(self, request, *args, **kwargs):
        resp = super().dispatch(request, *args, **kwargs)
        resp['X-Robots-Tag'] = "noindex"
        return resp


@cache_page(3600)
def robots_txt(request):
    return HttpResponse(
        """User-agent: *
Disallow: */cart/*
Disallow: */checkout/*
Disallow: */order/*
Disallow: */locale/set*
Disallow: /control/
Disallow: /download/
Disallow: /redirect/
Disallow: /api/
""", content_type='text/plain'
    )
