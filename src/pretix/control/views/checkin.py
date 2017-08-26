from django.db.models import F, Prefetch, Q
from django.db.models.functions import Coalesce
from django.views.generic import ListView

from pretix.base.models import Checkin, Item, OrderPosition
from pretix.control.permissions import EventPermissionRequiredMixin


class CheckInView(EventPermissionRequiredMixin, ListView):
    model = Checkin
    context_object_name = 'entries'
    paginate_by = 30
    template_name = 'pretixcontrol/checkin/index.html'
    permission = 'can_view_orders'

    def get_queryset(self):

        qs = OrderPosition.objects.filter(order__event=self.request.event, order__status='p')

        # if this setting is False, we check only items for admission
        if not self.request.event.settings.ticket_download_nonadm:
            qs = qs.filter(item__admission=True)

        if self.request.GET.get("status", "") != "":
            p = self.request.GET.get("status", "")
            if p == '1':
                # records with check-in record
                qs = qs.filter(checkins__isnull=False)
            elif p == '0':
                qs = qs.filter(checkins__isnull=True)

        if self.request.GET.get("user", "") != "":
            u = self.request.GET.get("user", "")
            qs = qs.filter(
                Q(order__email__icontains=u) | Q(attendee_name__icontains=u) | Q(attendee_email__icontains=u)
            )

        if self.request.GET.get("item", "") != "":
            u = self.request.GET.get("item", "")
            qs = qs.filter(item_id=u)

        if self.request.GET.get("subevent", "") != "":
            s = self.request.GET.get("subevent", "")
            qs = qs.filter(subevent_id=s)

        qs = qs.prefetch_related(
            Prefetch('checkins', queryset=Checkin.objects.filter(position__order__event=self.request.event))
        ).select_related('order', 'item', 'addon_to')

        if self.request.GET.get("ordering", "") != "":
            p = self.request.GET.get("ordering", "")
            keys_allowed = self.get_ordering_keys_mappings()
            if p in keys_allowed:
                mapped_field = keys_allowed[p]
                if isinstance(mapped_field, dict):
                    order = mapped_field.pop('_order')
                    qs = qs.annotate(**mapped_field).order_by(order)
                elif isinstance(mapped_field, (list, tuple)):
                    qs = qs.order_by(*mapped_field)
                else:
                    qs = qs.order_by(mapped_field)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = Item.objects.filter(event=self.request.event)
        ctx['filtered'] = ("status" in self.request.GET or "user" in self.request.GET or "item" in self.request.GET
                           or "subevent" in self.request.GET)
        return ctx

    @staticmethod
    def get_ordering_keys_mappings():
        return {
            'code': 'order__code',
            '-code': '-order__code',
            'email': 'order__email',
            '-email': '-order__email',
            # Set nulls_first to be consistent over databases
            'status': F('checkins__id').asc(nulls_first=True),
            '-status': F('checkins__id').desc(nulls_last=True),
            'timestamp': F('checkins__datetime').asc(nulls_first=True),
            '-timestamp': F('checkins__datetime').desc(nulls_last=True),
            'item': ('item__name', 'variation__value'),
            '-item': ('-item__name', 'variation__value'),
            'subevent': ('subevent__date_from', 'subevent__name'),
            '-subevent': ('-subevent__date_from', '-subevent__name'),
            'name': {'_order': F('display_name').asc(nulls_first=True),
                     'display_name': Coalesce('attendee_name', 'addon_to__attendee_name')},
            '-name': {'_order': F('display_name').desc(nulls_last=True),
                      'display_name': Coalesce('attendee_name', 'addon_to__attendee_name')},
        }
