import pytz
from django.db.models import Max, Min, Q
from django.db.models.functions import Coalesce, Greatest
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import ugettext as _

from pretix.control.utils.i18n import i18ncomp
from pretix.helpers.daterange import daterange


def event_list(request):
    query = request.GET.get('query', '')
    qs = request.user.get_events_with_any_permission().filter(
        Q(name__icontains=i18ncomp(query)) | Q(slug__icontains=query) |
        Q(organizer__name__icontains=i18ncomp(query)) | Q(organizer__slug__icontains=query)
    ).annotate(
        min_from=Min('subevents__date_from'),
        max_from=Max('subevents__date_from'),
        max_to=Max('subevents__date_to'),
        max_fromto=Greatest(Max('subevents__date_to'), Max('subevents__date_from'))
    ).annotate(
        order_from=Coalesce('min_from', 'date_from'),
    ).order_by('-order_from')

    def serialize(e):

        dr = e.get_date_range_display()
        if e.has_subevents:
            tz = pytz.timezone(e.settings.timezone)
            dr = _('Series:') + ' ' + daterange(
                e.min_from.astimezone(tz),
                (e.max_fromto or e.max_to or e.max_from).astimezone(tz)
            )
        return {
            'slug': e.slug,
            'organizer': str(e.organizer.name),
            'name': str(e.name),
            'date_range': dr,
            'url': reverse('control:event.index', kwargs={
                'event': e.slug,
                'organizer': e.organizer.slug
            })
        }

    doc = {
        'results': [
            serialize(e) for e in qs.select_related('organizer')[:10]
        ]
    }
    return JsonResponse(doc)
