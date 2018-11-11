from datetime import datetime, time

import pytz
from dateutil.parser import parse
from django.core.exceptions import PermissionDenied
from django.db.models import Max, Min, Q
from django.db.models.functions import Coalesce, Greatest
from django.http import JsonResponse
from django.urls import reverse
from django.utils.formats import get_format
from django.utils.timezone import make_aware
from django.utils.translation import pgettext, ugettext as _

from pretix.base.models import Organizer, User
from pretix.control.permissions import event_permission_required
from pretix.helpers.daterange import daterange
from pretix.helpers.i18n import i18ncomp


def serialize_user(u):
    return {
        'id': u.pk,
        'type': 'user',
        'name': str(u),
        'text': str(u),
        'url': reverse('control:index')
    }


def serialize_orga(o):
    return {
        'id': o.pk,
        'slug': o.slug,
        'type': 'organizer',
        'name': str(o.name),
        'text': str(o.name),
        'url': reverse('control:organizer', kwargs={
            'organizer': o.slug
        })
    }


def serialize_event(e):
    dr = e.get_date_range_display()
    if e.has_subevents:
        if e.min_from is None:
            dr = pgettext('subevent', 'No dates')
        else:
            tz = pytz.timezone(e.settings.timezone)
            dr = _('Series:') + ' ' + daterange(
                e.min_from.astimezone(tz),
                (e.max_fromto or e.max_to or e.max_from).astimezone(tz)
            )
    return {
        'id': e.pk,
        'slug': e.slug,
        'type': 'event',
        'organizer': str(e.organizer.name),
        'name': str(e.name),
        'text': str(e.name),
        'date_range': dr,
        'url': reverse('control:event.index', kwargs={
            'event': e.slug,
            'organizer': e.organizer.slug
        })
    }


def event_list(request):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
    qs = request.user.get_events_with_any_permission(request).filter(
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

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            serialize_event(e) for e in qs.select_related('organizer')[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


def nav_context_list(request):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
    qs_events = request.user.get_events_with_any_permission(request).filter(
        Q(name__icontains=i18ncomp(query)) | Q(slug__icontains=query)
    ).annotate(
        min_from=Min('subevents__date_from'),
        max_from=Max('subevents__date_from'),
        max_to=Max('subevents__date_to'),
        max_fromto=Greatest(Max('subevents__date_to'), Max('subevents__date_from'))
    ).annotate(
        order_from=Coalesce('min_from', 'date_from'),
    ).order_by('-order_from')

    if request.user.has_active_staff_session(request.session.session_key):
        qs_orga = Organizer.objects.all()
    else:
        qs_orga = Organizer.objects.filter(pk__in=request.user.teams.values_list('organizer', flat=True))
    qs_orga = qs_orga.filter(Q(name__icontains=query) | Q(slug__icontains=query))

    total = qs_events.count() + qs_orga.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    results = [
        serialize_user(request.user)
    ] + [
        serialize_orga(e) for e in qs_orga[offset:offset + pagesize]
    ] + [
        serialize_event(e) for e in qs_events.select_related('organizer')[offset:offset + pagesize]
    ]
    doc = {
        'results': results,
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

    qf = Q(name__icontains=i18ncomp(query)) | Q(location__icontains=query)
    tz = request.event.timezone

    dt = None
    for f in get_format('DATE_INPUT_FORMATS'):
        try:
            dt = datetime.strptime(query, f)
            break
        except (ValueError, TypeError):
            continue

    if dt:
        dt_start = make_aware(datetime.combine(dt.date(), time(hour=0, minute=0, second=0)), tz)
        dt_end = make_aware(datetime.combine(dt.date(), time(hour=23, minute=59, second=59)), tz)
        qf |= Q(date_from__gte=dt_start) & Q(date_from__lte=dt_end)

    qs = request.event.subevents.filter(
        qf
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


@event_permission_required(None)
def checkinlist_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    qf = Q(name__icontains=i18ncomp(query))

    try:
        dt = parse(query)
    except ValueError:
        pass
    else:
        tz = request.event.timezone
        if dt and request.event.has_subevents:
            dt_start = make_aware(datetime.combine(dt.date(), time(hour=0, minute=0, second=0)), tz)
            dt_end = make_aware(datetime.combine(dt.date(), time(hour=23, minute=59, second=59)), tz)
            qf |= Q(subevent__date_from__gte=dt_start) & Q(subevent__date_from__lte=dt_end)

    qs = request.event.checkin_lists.select_related('subevent').filter(
        qf
    ).order_by('name')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'text': str(e.name),
                'event': str(e.subevent) if request.event.has_subevents and e.subevent else None,
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@event_permission_required(None)
def itemvarquota_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    choices = []

    if not request.event.has_subevents:
        # We are very unlikely to need pagination
        itemqs = request.event.items.prefetch_related('variations').filter(name__icontains=i18ncomp(query))
        quotaqs = request.event.quotas.filter(name__icontains=query)
        more = False
    else:
        # We can't do proper pagination on a UNION-like query, so we hack it.
        if query:
            # Don't paginate
            quotaf = Q(name__icontains=query)
            try:
                dt = parse(query)
            except ValueError:
                pass
            else:
                tz = request.event.timezone
                if dt and request.event.has_subevents:
                    dt_start = make_aware(datetime.combine(dt.date(), time(hour=0, minute=0, second=0)), tz)
                    dt_end = make_aware(datetime.combine(dt.date(), time(hour=23, minute=59, second=59)), tz)
                    quotaf |= Q(subevent__date_from__gte=dt_start) & Q(subevent__date_from__lte=dt_end)

            itemqs = request.event.items.prefetch_related('variations').filter(
                Q(name__icontains=i18ncomp(query)) | Q(internal_name__icontains=query)
            )
            quotaqs = request.event.quotas.filter(quotaf).select_related('subevent')
            more = False
        else:
            if page == 1:
                itemqs = request.event.items.prefetch_related('variations').filter(
                    Q(name__icontains=i18ncomp(query)) | Q(internal_name__icontains=query)
                )
            else:
                itemqs = request.event.items.none()
            quotaqs = request.event.quotas.filter(name__icontains=query).select_related('subevent')
            total = quotaqs.count()
            pagesize = 20
            offset = (page - 1) * pagesize
            quotaqs = quotaqs[offset:offset + pagesize]
            more = total >= (offset + pagesize)

    for i in itemqs:
        variations = list(i.variations.all())
        if variations:
            choices.append((str(i.pk), _('{product} – Any variation').format(product=i), ''))
            for v in variations:
                choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (i, v.value), ''))
        else:
            choices.append((str(i.pk), str(i), ''))
    for q in quotaqs:
        if request.event.has_subevents:
            choices.append(('q-%d' % q.pk,
                            _('Any product in quota "{quota}"').format(
                                quota=q
                            ), str(q.subevent)))
        else:
            choices.append(('q-%d' % q.pk, _('Any product in quota "{quota}"').format(quota=q), ''))

    doc = {
        'results': [
            {
                'id': k,
                'text': str(v),
                'event': str(t),
            }
            for k, v, t in choices
        ],
        'pagination': {
            "more": more
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
    if not request.user.has_active_staff_session(request.session.session_key):
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
    if not request.user.has_active_staff_session(request.session.session_key):
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
