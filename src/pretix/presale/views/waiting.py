from django.contrib import messages
from django.shortcuts import redirect
from django.utils import translation
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView

from ...base.models import Item, ItemVariation, WaitingListEntry
from ...multidomain.urlreverse import eventreverse
from ..forms.waitinglist import WaitingListForm


class WaitingView(FormView):
    template_name = 'pretixpresale/event/waitinglist.html'
    form_class = WaitingListForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        kwargs['instance'] = WaitingListEntry(
            item=self.item_and_variation[0], variation=self.item_and_variation[1],
            event=self.request.event, locale=translation.get_language()
        )
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['event'] = self.request.event
        ctx['item'], ctx['variation'] = self.item_and_variation
        return ctx

    @cached_property
    def item_and_variation(self):
        try:
            item = self.request.event.items.get(pk=self.request.GET.get('item'))
            if 'var' in self.request.GET:
                var = item.variations.get(pk=self.request.GET['var'])
            elif item.has_variations:
                return None
            else:
                var = None
            return item, var
        except (Item.DoesNotExist, ItemVariation.DoesNotExist):
            return None

    def dispatch(self, request, *args, **kwargs):
        self.request = request

        if not self.request.event.settings.waiting_list_enabled:
            messages.error(request, _("Waiting lists are disabled for this event."))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        if not self.item_and_variation:
            messages.error(request, _("We could not identify the product you selected."))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        availability = (
            self.item_and_variation[1].check_quotas(count_waitinglist=False)
            if self.item_and_variation[1]
            else self.item_and_variation[0].check_quotas(count_waitinglist=False)
        )
        if availability[0] == 100:
            messages.error(self.request, _("You cannot add yourself to the waiting list as this product is currently "
                                           "available."))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        form.save()
        messages.success(self.request, _("We've added you to the waiting list. You will receive "
                                         "an email as soon as tickets get available again."))
        return super().form_valid(form)

    def get_success_url(self):
        return eventreverse(self.request.event, 'presale:event.index')
