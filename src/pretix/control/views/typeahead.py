from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse

from pretix.control.utils.i18n import i18ncomp


def event_list(request):
    query = request.GET.get('query', '')
    qs = request.user.get_events_with_any_permission().filter(
        Q(name__icontains=i18ncomp(query)) | Q(slug__icontains=query) |
        Q(organizer__name__icontains=i18ncomp(query)) | Q(organizer__slug__icontains=query)
    ).order_by('-date_from')
    doc = {
        'results': [
            {
                'slug': e.slug,
                'organizer': str(e.organizer.name),
                'name': str(e.name),
                'date_range': e.get_date_range_display(),
                'url': reverse('control:event.index', kwargs={
                    'event': e.slug,
                    'organizer': e.organizer.slug
                })
            } for e in qs.select_related('organizer')[:10]
        ]
    }
    return JsonResponse(doc)
