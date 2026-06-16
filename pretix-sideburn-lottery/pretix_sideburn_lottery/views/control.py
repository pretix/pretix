from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View

from pretix.base.models import Item
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views.waitinglist import WaitingListQuerySetMixin

from ..services.lottery import run_lottery


class BaseLotteryView(EventPermissionRequiredMixin, WaitingListQuerySetMixin, View):
    permission = "can_change_orders"
    revert = False

    def _waitinglist_url(self):
        return reverse(
            "control:event.orders.waitinglist",
            kwargs={
                "event": self.request.event.slug,
                "organizer": self.request.event.organizer.slug,
            },
        )

    def get(self, request, *args, **kwargs):
        item_id = request.GET.get("item", "")
        if not item_id:
            messages.error(
                request,
                _("You must select a product to run or revert its lottery."),
            )
            return redirect(self._waitinglist_url())

        try:
            Item.objects.get(pk=item_id, event=request.event)
        except (ValueError, Item.DoesNotExist):
            messages.error(request, _("Invalid product selected."))
            return redirect(self._waitinglist_url())

        response = run_lottery(
            request.event,
            self.get_queryset(),
            item_id,
            revert=self.revert,
        )
        if response is None:
            messages.error(
                request,
                _("No waiting list entries found for the selected product."),
            )
            return redirect(self._waitinglist_url())

        return response


class RunLotteryView(BaseLotteryView):
    revert = False


class RevertLotteryView(BaseLotteryView):
    revert = True
