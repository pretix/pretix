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
from django.conf.urls import include, re_path

from pretix.multidomain import event_url

from .views import (
    abort, isu_disconnect, isu_return, redirect_view, success, webhook, PayView, XHRView,
)

event_patterns = [
    re_path(r'^paypal/', include([
        re_path(r'^abort/$', abort, name='abort'),
        re_path(r'^return/$', success, name='return'),
        re_path(r'^redirect/$', redirect_view, name='redirect'),
        re_path(r'^xhr/$', XHRView.as_view(), name='xhr'),
        re_path(r'^pay/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[^/]+)/$', PayView.as_view(), name='pay'),
        re_path(r'^(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/xhr/$', XHRView.as_view(), name='xhr'),

        re_path(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/abort/', abort, name='abort'),
        re_path(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/return/', success, name='return'),
        re_path(r'w/(?P<cart_namespace>[a-zA-Z0-9]{16})/xhr/', XHRView.as_view(), name='xhr'),

        event_url(r'^webhook/$', webhook, name='webhook', require_live=False),
    ])),
]

urlpatterns = [
    re_path(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/paypal/disconnect/',
            isu_disconnect, name='oauth.disconnect'),
    re_path(r'^_paypal/webhook/$', webhook, name='webhook'),
    re_path(r'^_paypal/oauth_return/$', isu_return, name='oauth.return'),
]
