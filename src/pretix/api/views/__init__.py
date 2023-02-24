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
from calendar import timegm

from django.db.models import Max
from django.http import HttpResponse
from django.utils.http import http_date, parse_http_date_safe

from pretix.api.pagination import TotalOrderingFilter


class RichOrderingFilter(TotalOrderingFilter):

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)

        if ordering:
            if hasattr(view, 'ordering_custom'):
                newo = []
                for ordering_part in ordering:
                    ob = view.ordering_custom.get(ordering_part)
                    if ob:
                        ob = dict(ob)
                        newo.append(ob.pop('_order'))
                        queryset = queryset.annotate(**ob)
                    else:
                        newo.append(ordering_part)
                ordering = newo
            return queryset.order_by(*ordering)

        return queryset


class ConditionalListView:

    def list(self, request, **kwargs):
        if_modified_since = request.headers.get('If-Modified-Since')
        if if_modified_since:
            if_modified_since = parse_http_date_safe(if_modified_since)
        if_unmodified_since = request.headers.get('If-Unmodified-Since')
        if if_unmodified_since:
            if_unmodified_since = parse_http_date_safe(if_unmodified_since)
        if not hasattr(request, 'event'):
            return super().list(request, **kwargs)

        lmd = request.event.logentry_set.filter(
            content_type__model=self.get_queryset().model._meta.model_name,
            content_type__app_label=self.get_queryset().model._meta.app_label,
        ).aggregate(
            m=Max('datetime')
        )['m']
        if lmd:
            lmd_ts = timegm(lmd.utctimetuple())

        if if_unmodified_since and lmd and lmd_ts > if_unmodified_since:
            return HttpResponse(status=412)

        if if_modified_since and lmd and lmd_ts <= if_modified_since:
            return HttpResponse(status=304)

        resp = super().list(request, **kwargs)
        if lmd:
            resp['Last-Modified'] = http_date(lmd_ts)
        return resp
