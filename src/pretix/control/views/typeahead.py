import pytz
from django.core.exceptions import PermissionDenied
from django.db.models import Max, Min, Q
from django.db.models.functions import Coalesce, Greatest
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import ugettext as _

from pretix.base.models import Organizer, User
from pretix.control.permissions import event_permission_required
from pretix.helpers.daterange import daterange
from pretix.helpers.i18n import i18ncomp


def event_list(request):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
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
            'id': e.pk,
            'slug': e.slug,
            'organizer': str(e.organizer.name),
            'name': str(e.name),
            'text': str(e.name),
            'date_range': dr,
            'url': reverse('control:event.index', kwargs={
                'event': e.slug,
                'organizer': e.organizer.slug
            })
        }

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            serialize(e) for e in qs.select_related('organizer')[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@event_permission_required(None)
def subevent_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    qs = request.event.subevents.filter(
        Q(name__icontains=i18ncomp(query)) | Q(location__icontains=query)
    ).order_by('-date_from')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'name': str(e.name),
                'date_range': e.get_date_range_display(),
                'text': '{} – {}'.format(e.name, e.get_date_range_display()),
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


def organizer_select2(request):
    term = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
    qs = Organizer.objects.all()
    if term:
        qs = qs.filter(Q(name__icontains=term) | Q(slug__icontains=term))
    if not request.user.is_superuser:
        qs = qs.filter(pk__in=request.user.teams.values_list('organizer', flat=True))

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize

    doc = {
        "results": [
            {
                'id': o.pk,
                'text': str(o.name)
            } for o in qs[offset:offset + pagesize]
        ],
        "pagination": {
            "more": total >= (offset + pagesize)
        }
    }

    return JsonResponse(doc)


def users_select2(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    term = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
    qs = User.objects.all()
    if term:
        qs = qs.filter(Q(email__icontains=term) | Q(fullname__icontains=term))

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize

    doc = {
        "results": [
            {
                'id': o.pk,
                'text': str(o.email)
            } for o in qs[offset:offset + pagesize]
        ],
        "pagination": {
            "more": total >= (offset + pagesize)
        }
    }

    return JsonResponse(doc)
