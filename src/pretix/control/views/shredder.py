import logging
from collections import OrderedDict

from django.utils.functional import cached_property
from django.views.generic import TemplateView

from pretix.base.shredder import shred_constraints
from pretix.control.permissions import EventPermissionRequiredMixin

logger = logging.getLogger(__name__)


class ShredderMixin:

    @cached_property
    def shredders(self):
        return OrderedDict(
            sorted(self.request.event.get_data_shredders().items(), key=lambda s: s[1].verbose_name)
        )


class StartShredView(EventPermissionRequiredMixin, ShredderMixin, TemplateView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/shredder/index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['shredders'] = self.shredders
        ctx['constraints'] = shred_constraints(self.request.event)
        return ctx
