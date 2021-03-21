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
# This file contains Apache-licensed contributions copyrighted by: Jonas Große Sundrup
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import base64
import hmac

from django.conf import settings
from django.http import HttpResponse
from django_scopes import scopes_disabled

from .. import metrics


def unauthed_response():
    content = "<html><title>Forbidden</title><body>You are not authorized to view this page.</body></html>"
    response = HttpResponse(content, content_type="text/html")
    response["WWW-Authenticate"] = 'Basic realm="metrics"'
    response.status_code = 401
    return response


@scopes_disabled()
def serve_metrics(request):
    if not settings.METRICS_ENABLED:
        return unauthed_response()

    # check if the user is properly authorized:
    if "Authorization" not in request.headers:
        return unauthed_response()

    method, credentials = request.headers["Authorization"].split(" ", 1)
    if method.lower() != "basic":
        return unauthed_response()

    user, passphrase = base64.b64decode(credentials.strip()).decode().split(":", 1)

    if not hmac.compare_digest(user, settings.METRICS_USER):
        return unauthed_response()
    if not hmac.compare_digest(passphrase, settings.METRICS_PASSPHRASE):
        return unauthed_response()

    # ok, the request passed the authentication-barrier, let's hand out the metrics:
    m = metrics.metric_values()

    output = []
    for metric, sub in m.items():
        for label, value in sub.items():
            output.append("{}{} {}".format(metric, label, str(value)))

    content = "\n".join(output) + "\n"

    return HttpResponse(content)
