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
import logging

from dateutil.parser import parse
from django.http import HttpRequest
from django.urls import resolve
from django.utils.timezone import now
from django_scopes import scope
from rest_framework.response import Response

from pretix.base.middleware import LocaleMiddleware
from pretix.base.models import Event, Organizer
from pretix.base.timemachine import timemachine_now_var

logger = logging.getLogger(__name__)


class ApiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        if not request.path.startswith("/storefrontapi/"):
            return self.get_response(request)

        url = resolve(request.path_info)
        try:
            request.organizer = Organizer.objects.filter(
                slug=url.kwargs["organizer"],
            ).first()
        except Organizer.DoesNotExist:
            return Response(
                {"detail": "Organizer not found."},
                status=404,
            )

        with scope(organizer=getattr(request, "organizer", None)):
            # todo: Authorization
            is_authorized_public = False  # noqa
            is_authorized_private = True
            sales_channel_id = "web"  # todo: get form authorization

            if "event" in url.kwargs:
                try:
                    request.event = request.organizer.events.get(
                        slug=url.kwargs["event"],
                        organizer=request.organizer,
                    )

                    if not request.event.live and not is_authorized_private:
                        return Response(
                            {"detail": "Event not live."},
                            status=403,
                        )

                except Event.DoesNotExist:
                    return Response(
                        {"detail": "Event not found."},
                        status=404,
                    )

            try:
                request.sales_channel = request.organizer.sales_channels.get(
                    identifier=sales_channel_id
                )

                if (
                    "X-Storefront-Time-Machine-Date" in request.headers
                    and "event" in url.kwargs
                ):
                    if not request.event.testmode:
                        return Response(
                            {
                                "detail": "Time machine can only be used for events in test mode."
                            },
                            status=400,
                        )
                    try:
                        time_machine_date = parse(
                            request.headers["X-Storefront-Time-Machine-Date"]
                        )
                    except ValueError:
                        return Response(
                            {"detail": "Invalid time machine header"},
                            status=400,
                        )
                    else:
                        request.now_dt = time_machine_date
                        request.now_dt_is_fake = True
                        timemachine_now_var.set(
                            request.now_dt if request.now_dt_is_fake else None
                        )
                else:
                    request.now_dt = now()
                    request.now_dt_is_fake = False

                if (
                    not request.event.all_sales_channels
                    and request.sales_channel.identifier
                    not in (
                        s.identifier for s in request.event.limit_sales_channels.all()
                    )
                ):
                    return Response(
                        {"detail": "Event not available on this sales channel."},
                        status=403,
                    )

                LocaleMiddleware(NotImplementedError).process_request(request)
                r = self.get_response(request)
                r["Access-Control-Allow-Origin"] = "*"  # todo: allow whitelist?
                r["Access-Control-Allow-Methods"] = ", ".join(
                    [
                        "GET",
                        "POST",
                        "HEAD",
                        "OPTIONS",
                        "PUT",
                        "DELETE",
                    ]
                )
                r["Access-Control-Allow-Headers"] = ", ".join(
                    [
                        "Content-Type",
                        "X-Storefront-Time-Machine-Date",
                        "Accept",
                        "Accept-Language",
                    ]
                )
                return r
            finally:
                timemachine_now_var.set(None)
