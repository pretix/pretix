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
from django.template.response import TemplateResponse
from django.urls import resolve
from django_scopes import scope

from pretix.base.channels import WebshopSalesChannel
from pretix.presale.signals import process_response

from .utils import _detect_event


class EventMiddleware:
    NO_REQUIRE_LIVE_URLS = {
        'event.widget.productlist',
        'event.widget.css',
    }

    def __init__(self, get_response=None):
        self.get_response = get_response
        super().__init__()

    def __call__(self, request):
        url = resolve(request.path_info)
        request._namespace = url.namespace

        if not hasattr(request, 'sales_channel'):
            # The environ lookup is only relevant during unit testing
            request.sales_channel = request.environ.get('PRETIX_SALES_CHANNEL', WebshopSalesChannel())

        if url.namespace != 'presale':
            return self.get_response(request)

        if 'organizer' in url.kwargs or 'event' in url.kwargs or getattr(request, 'event_domain', False):
            redirect = _detect_event(request, require_live=url.url_name not in self.NO_REQUIRE_LIVE_URLS)
            if redirect:
                return redirect

        with scope(organizer=getattr(request, 'organizer', None)):
            response = self.get_response(request)

            if hasattr(request, '_namespace') and request._namespace == 'presale' and hasattr(request, 'event'):
                for receiver, r in process_response.send(request.event, request=request, response=response):
                    response = r

            if isinstance(response, TemplateResponse):
                response = response.render()

        return response
