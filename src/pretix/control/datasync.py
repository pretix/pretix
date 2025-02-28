from django.contrib import messages
from django.dispatch import receiver
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.loader import get_template

from pretix.base.datasync.datasync import sync_targets
from pretix.base.models import Event, Order
from pretix.control.signals import order_info
from pretix.control.views.orders import OrderView
from django.utils.translation import gettext_lazy as _

@receiver(order_info, dispatch_uid="datasync_control_order_info")
def on_control_order_info(sender: Event, request, order: Order, **kwargs):
    providers = [provider for provider, meta in sync_targets.filter(active_in=sender)]
    if not providers: return ""

    queued = order.queued_sync_jobs.all()
    queued_provider_ids = {p.sync_provider for p in queued}
    non_pending = [(provider.identifier, provider.display_name) for provider in providers if provider.identifier not in queued_provider_ids]

    #sync_logs = order.all_logentries().filter(action_type__in=(
    #    "pretix.event.order.data_sync.success",
    #    "pretix.event.order.data_sync.failed"
    #))

    template = get_template("pretixcontrol/datasync/control_order_info.html")
    ctx = {
        "order": order,
        "request": request,
        "event": sender,
        "non_pending_providers": non_pending,
        "queued_sync_jobs": queued,
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
