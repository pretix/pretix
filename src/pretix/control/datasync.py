#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2025 rami.io GmbH and contributors
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

from itertools import groupby

from django.contrib import messages
from django.dispatch import receiver
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _

from pretix.base.datasync.datasync import sync_targets
from pretix.base.models import Event, Order
from pretix.control.signals import order_info
from pretix.control.views.orders import OrderView


@receiver(order_info, dispatch_uid="datasync_control_order_info")
def on_control_order_info(sender: Event, request, order: Order, **kwargs):
    providers = [provider for provider, meta in sync_targets.filter(active_in=sender)]
    if not providers:
        return ""

    queued = {p.sync_provider: p for p in order.queued_sync_jobs.all()}
    objects = {
        provider: list(objects)
        for (provider, objects)
        in groupby(order.synced_objects.order_by('sync_provider').all(), key=lambda o: o.sync_provider)
    }
    providers = [(provider.identifier, provider.display_name, queued.get(provider.identifier), objects.get(provider.identifier)) for provider in providers]

    template = get_template("pretixcontrol/datasync/control_order_info.html")
    ctx = {
        "order": order,
        "request": request,
        "event": sender,
        "providers": providers,
    }
    return template.render(ctx, request=request)


class ControlSyncJob(OrderView):
    permission = 'can_change_orders'

    def post(self, request, provider, *args, **kwargs):
        prov, meta = sync_targets.get(active_in=self.request.event, identifier=provider)

        if self.request.POST.get("queue_sync") == "true":
            prov.enqueue_order(self.order, 'user')
            messages.success(self.request, _('The sync job has been enqueued and will run in the next minutes.'))
        elif self.request.POST.get("cancel_job"):
            job = self.order.queued_sync_jobs.get(pk=self.request.POST.get("cancel_job"))
            job.delete()
            messages.success(self.request, _('The sync job has been canceled.'))
        elif self.request.POST.get("run_job_now"):
            job = self.order.queued_sync_jobs.get(pk=self.request.POST.get("run_job_now"))
            job.not_before = None
            job.save()
            messages.success(self.request, _('The sync job has been set to run as soon as possible.'))

        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])
