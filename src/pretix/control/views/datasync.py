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

from itertools import groupby

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.dispatch import receiver
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.loader import get_template
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView

from pretix.base.datasync.datasync import datasync_providers
from pretix.base.models import Event, Order
from pretix.base.models.datasync import OrderSyncQueue
from pretix.base.services.datasync import sync_single
from pretix.control.permissions import (
    AdministratorPermissionRequiredMixin, EventPermissionRequiredMixin,
    OrganizerPermissionRequiredMixin,
)
from pretix.control.signals import order_info
from pretix.control.views.orders import OrderView
from pretix.helpers import OF_SELF


@receiver(order_info, dispatch_uid="datasync_control_order_info")
def on_control_order_info(sender: Event, request, order: Order, **kwargs):
    providers = [provider for provider, meta in datasync_providers.filter(active_in=sender)]
    if not providers:
        return ""

    queued = {p.sync_provider: p for p in order.queued_sync_jobs.all()}
    objects = {
        provider: list(objects)
        for (provider, objects)
        in groupby(order.sync_results.order_by('sync_provider').all(), key=lambda o: o.sync_provider)
    }
    providers = [(provider.identifier, provider.display_name, queued.get(provider.identifier), objects.get(provider.identifier)) for provider in providers]

    template = get_template("pretixcontrol/datasync/control_order_info.html")
    ctx = {
        "order": order,
        "request": request,
        "event": sender,
        "providers": providers,
        "now": now(),
    }
    return template.render(ctx, request=request)


class ControlSyncJob(OrderView):
    permission = 'can_change_orders'

    def post(self, request, provider, *args, **kwargs):
        prov, meta = datasync_providers.get(active_in=self.request.event, identifier=provider)

        if self.request.POST.get("queue_sync") == "true":
            prov.enqueue_order(self.order, 'user', immediate=True)
            messages.success(self.request, _('The sync job has been set to run as soon as possible.'))
        elif self.request.POST.get("cancel_job"):
            with transaction.atomic():
                try:
                    job = self.order.queued_sync_jobs.select_for_update(of=OF_SELF).get(
                        pk=self.request.POST.get("cancel_job")
                    )
                except OrderSyncQueue.DoesNotExist:
                    messages.info(self.request, _('The sync job could not be found. It may have been processed in the meantime.'))
                else:
                    if job.in_flight:
                        messages.warning(self.request, _('The sync job is already in progress.'))
                    else:
                        job.delete()
                        messages.success(self.request, _('The sync job has been canceled.'))
        elif self.request.POST.get("run_job_now"):
            with transaction.atomic():
                try:
                    job = self.order.queued_sync_jobs.select_for_update(of=OF_SELF).get(
                        pk=self.request.POST.get("run_job_now")
                    )
                except OrderSyncQueue.DoesNotExist:
                    messages.info(self.request, _('The sync job could not be found. It may have been processed in the meantime.'))
                else:
                    if job.in_flight:
                        messages.success(self.request, _('The sync job is already in progress.'))
                    else:
                        job.not_before = now()
                        job.need_manual_retry = None
                        job.save()
                        sync_single.apply_async(args=(job.pk,))
                        messages.success(self.request, _('The sync job has been set to run as soon as possible.'))

        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class FailedSyncJobsView(ListView):
    template_name = 'pretixcontrol/datasync/failed_jobs.html'
    model = OrderSyncQueue
    context_object_name = 'queue_items'
    paginate_by = 100
    ordering = ('triggered',)

    def get_queryset(self):
        return super().get_queryset().filter(
            Q(need_manual_retry__isnull=False)
            | Q(failed_attempts__gt=0)
        ).select_related(
            'order'
        )

    def post(self, request, *args, **kwargs):
        items = self.get_queryset().filter(pk__in=request.POST.getlist('idlist'))

        if self.request.POST.get("action") == "retry":
            for item in items:
                item.not_before = now()
                item.need_manual_retry = None
                item.save()
            messages.success(self.request, _('The selected jobs have been set to run as soon as possible.'))
        elif self.request.POST.get("action") == "cancel":
            items.delete()
            messages.success(self.request, _('The selected jobs have been canceled.'))

        return redirect(request.get_full_path())


class GlobalFailedSyncJobsView(AdministratorPermissionRequiredMixin, FailedSyncJobsView):
    pass


class OrganizerFailedSyncJobsView(OrganizerPermissionRequiredMixin, FailedSyncJobsView):
    permission = "can_change_organizer_settings"

    def get_queryset(self):
        return super().get_queryset().filter(
            event__organizer=self.request.organizer
        )


class EventFailedSyncJobsView(EventPermissionRequiredMixin, FailedSyncJobsView):
    permission = "can_change_event_settings"

    def get_queryset(self):
        return super().get_queryset().filter(
            event=self.request.event
        )
