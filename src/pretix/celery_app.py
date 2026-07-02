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
import logging
import os

from celery import Celery, signals
from django.dispatch import receiver

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pretix.settings")
logger = logging.getLogger(__name__)

from django.conf import settings

app = Celery('pretix')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@receiver(signals.before_task_publish)
def on_before_task_publish(sender, body, exchange, routing_key, headers, properties, declare, retry_policy, **kwargs):
    from pretix.helpers.logs import local

    trace = getattr(local, 'trace', [])
    request_id = getattr(local, 'request_id', None)
    if request_id:
        trace.append(request_id)

    headers["X-Pretix-Trace"] = " ".join(trace)


@receiver(signals.task_received)
def on_task_received(sender, request, **kwargs):
    trace = request._request_dict.get("X-Pretix-Trace")
    if trace:
        logger.info(f"Task {request.id} has trace {trace}")


@receiver(signals.task_prerun)
def on_task_prerun(sender, task_id, task, **kwargs):
    from pretix.helpers.logs import local

    if "X-Pretix-Trace" in task.request.headers:
        local.trace = task.request.headers["X-Pretix-Trace"].split(" ")
    else:
        local.trace = []
    local.trace.append(task_id)


@receiver(signals.task_postrun)
def on_task_postrun(sender, task_id, task, **kwargs):
    from pretix.helpers.logs import local

    local.request_id = None
    local.trace = []
