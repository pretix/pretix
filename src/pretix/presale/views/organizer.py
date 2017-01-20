from django.db.models import Q
from django.utils.timezone import now
from django.views.generic import ListView

from pretix.base.models import Event
from pretix.presale.views import OrganizerViewMixin


class OrganizerIndex(OrganizerViewMixin, ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'pretixpresale/organizers/index.html'
    paginate_by = 30

    def get_queryset(self):
        query = Q(is_public=True)
        if "old" in self.request.GET:
            query &= Q(Q(date_from__lte=now()) & Q(date_to__lte=now()))
            order = '-date_from'
        else:
            query &= Q(Q(date_from__gte=now()) | Q(date_to__gte=now()))
            order = 'date_from'
        return Event.objects.filter(
            Q(organizer=self.request.organizer) & query
        ).order_by(order)
