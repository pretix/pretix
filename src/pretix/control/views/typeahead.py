#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from datetime import datetime, time
from zoneinfo import ZoneInfo

from dateutil.parser import parse
from django.core.exceptions import PermissionDenied
from django.db.models import F, Max, Min, Q
from django.db.models.functions import Coalesce, Greatest
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.formats import date_format, get_format
from django.utils.timezone import make_aware
from django.utils.translation import gettext as _, pgettext

from pretix.base.models import (
    EventMetaProperty, EventMetaValue, ItemMetaProperty, ItemMetaValue,
    ItemVariation, ItemVariationMetaValue, Order, OrderPosition, Organizer,
    SubEventMetaValue, User, Voucher,
)
from pretix.control.forms.event import EventWizardCopyForm
from pretix.control.permissions import (
    event_permission_required, organizer_permission_required,
)
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
            tz = ZoneInfo(e.settings.timezone)
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


def serialize_order(o):
    return {
        'type': 'order',
        'event': str(o.event),
        'title': _('Order {}').format(str(o.code)),
        'url': reverse('control:event.order', kwargs={
            'event': o.event.slug,
            'organizer': o.event.organizer.slug,
            'code': o.code
        })
    }


def serialize_voucher(v):
    return {
        'type': 'voucher',
        'event': str(v.event),
        'title': _('Voucher {}').format(str(v.code)),
        'url': reverse('control:event.voucher', kwargs={
            'event': v.event.slug,
            'organizer': v.event.organizer.slug,
            'voucher': v.pk
        })
    }


def event_list(request):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    if 'can_copy' in request.GET:
        qs = EventWizardCopyForm.copy_from_queryset(request.user, request.session)
    else:
        qs = request.user.get_events_with_any_permission(request)

    qs = qs.filter(
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


@organizer_permission_required(("can_manage_gift_cards", "can_manage_reusable_media"))
def giftcard_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    if request.user.has_organizer_permission(request.organizer, 'can_manage_gift_cards', request):
        qs = request.organizer.issued_gift_cards.filter(
            Q(secret__icontains=query)
        ).order_by('secret')
    else:
        qs = request.organizer.issued_gift_cards.filter(
            Q(secret__iexact=query)
        ).order_by('secret')

    if not query:
        qs = qs.none()

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'text': str(e),
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@organizer_permission_required(("can_manage_reusable_media", "can_manage_gift_cards"))
def ticket_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    qs_orders = OrderPosition.all.select_related('order', 'order__event', 'item', 'variation').filter(
        order__event__organizer=request.organizer,
    ).order_by()

    exact_match = Q(secret__iexact=query)
    soft_match = Q(secret__icontains=query)

    qsplit = query.split("-")

    if len(qsplit) >= 3 and qsplit[2].isdigit():
        soft_match |= Q(order__event__slug__iexact=qsplit[0], order__code__iexact=qsplit[1], positionid=qsplit[2])
    elif len(qsplit) >= 2 and qsplit[1].isdigit():
        soft_match |= Q(order__code__istartswith=qsplit[0], positionid=qsplit[1])
    elif len(qsplit) >= 2:
        soft_match |= Q(order__event__slug__iexact=qsplit[0], order__code__istartswith=qsplit[1])
    else:
        soft_match |= Q(order__code__istartswith=qsplit[0])

    if not request.user.has_active_staff_session(request.session.session_key):
        qs_orders = qs_orders.filter(
            exact_match | (
                soft_match & (
                    Q(order__event__organizer_id__in=request.user.teams.filter(all_events=True, can_view_orders=True).values_list('organizer', flat=True))
                    | Q(order__event_id__in=request.user.teams.filter(can_view_orders=True).values_list('limit_events__id', flat=True))
                )
            )
        )
    else:
        qs_orders = qs_orders.filter(exact_match | soft_match)

    if not query:
        qs_orders = qs_orders.none()

    total = qs_orders.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': op.pk,
                'text': f'{op.order.code}-{op.positionid} ({str(op.item) + ((" - " + str(op.variation)) if op.variation else "")})',
                'event': str(op.order.event)
            }
            for op in qs_orders[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@organizer_permission_required("can_manage_customers")
def customer_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    qs = request.organizer.customers.filter(
        Q(email__icontains=query) | Q(name_cached__icontains=query) | Q(identifier__istartswith=query)
    ).order_by('name_cached')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'text': str(e),
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


def nav_context_list(request):
    query = request.GET.get('query', '').strip()
    organizer = request.GET.get('organizer', None)

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
    if query:
        qs_orga = qs_orga.filter(Q(name__icontains=query) | Q(slug__icontains=query))

    if query and len(query) >= 3:
        qs_orders = Order.objects.filter(
            code__istartswith=query
        ).select_related('event', 'event__organizer').only('event', 'code', 'pk').order_by()
        if not request.user.has_active_staff_session(request.session.session_key):
            qs_orders = qs_orders.filter(
                Q(event__organizer_id__in=request.user.teams.filter(
                    all_events=True, can_view_orders=True).values_list('organizer', flat=True))
                | Q(event_id__in=request.user.teams.filter(
                    can_view_orders=True).values_list('limit_events__id', flat=True))
            )

        qs_vouchers = Voucher.objects.filter(
            code__istartswith=query
        ).select_related('event', 'event__organizer').only('event', 'code', 'pk').order_by()
        if not request.user.has_active_staff_session(request.session.session_key):
            qs_vouchers = qs_vouchers.filter(
                Q(event__organizer_id__in=request.user.teams.filter(
                    all_events=True, can_view_vouchers=True).values_list('organizer', flat=True))
                | Q(event_id__in=request.user.teams.filter(
                    can_view_vouchers=True).values_list('limit_events__id', flat=True))
            )
    else:
        qs_vouchers = Voucher.objects.none()
        qs_orders = Order.objects.none()

    show_user = not query or (
        query and request.user.email and query.lower() in request.user.email.lower()
    ) or (
        query and request.user.fullname and query.lower() in request.user.fullname.lower()
    )
    total = qs_events.count() + qs_orga.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    results = ([
        serialize_user(request.user)
    ] if show_user else []) + [
        serialize_orga(e) for e in qs_orga[offset:offset + (pagesize if query else 5)]
    ] + [
        serialize_event(e) for e in qs_events.select_related('organizer')[offset:offset + (pagesize if query else 5)]
    ] + [
        serialize_order(e) for e in qs_orders[offset:offset + (pagesize if query else 5)]
    ] + [
        serialize_voucher(e) for e in qs_vouchers[offset:offset + (pagesize if query else 5)]
    ]

    if show_user and organizer:
        try:
            organizer = Organizer.objects.get(pk=organizer)
        except Organizer.DoesNotExist:
            pass
        else:
            if request.user.has_organizer_permission(organizer, request=request):
                organizer = serialize_orga(organizer)
                if organizer in results:
                    results.remove(organizer)
                results.insert(1, organizer)

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
    ).order_by('-date_from', 'name', 'pk')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'name': str(e.name),
                'date_range': e.get_date_range_display() + (
                    " " + date_format(e.date_from.astimezone(tz), "TIME_FORMAT") if e.settings.show_times else ""
                ),
                'text': str(e)
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@event_permission_required(None)
def quotas_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    qf = Q(name__icontains=query) | Q(subevent__name__icontains=i18ncomp(query))
    tz = request.event.timezone

    dt = None
    for f in get_format('DATE_INPUT_FORMATS'):
        try:
            dt = datetime.strptime(query, f)
            break
        except (ValueError, TypeError):
            continue

    if dt and request.event.has_subevents:
        dt_start = make_aware(datetime.combine(dt.date(), time(hour=0, minute=0, second=0)), tz)
        dt_end = make_aware(datetime.combine(dt.date(), time(hour=23, minute=59, second=59)), tz)
        qf |= Q(subevent__date_from__gte=dt_start) & Q(subevent__date_from__lte=dt_end)

    qs = request.event.quotas.filter(
        qf
    ).order_by('-subevent__date_from', 'name')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': q.pk,
                'name': str(q.name),
                'text': q.name
            }
            for q in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@event_permission_required(None)
def items_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    q = Q(name__icontains=i18ncomp(query)) | Q(internal_name__icontains=query)
    try:
        if query.isdigit():
            q |= Q(pk=int(query))
    except ValueError:
        pass
    qs = request.event.items.filter(q).order_by(
        F('category__position').asc(nulls_first=True),
        'category',
        'position',
        'pk'
    )

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'text': str(e),
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@event_permission_required(None)
def variations_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    q = Q(item__event=request.event)
    for word in query.split():
        q &= Q(value__icontains=i18ncomp(word)) | Q(item__name__icontains=i18ncomp(ord))

    qs = ItemVariation.objects.filter(q).order_by(
        F('item__category__position').asc(nulls_first=True),
        'item__category_id',
        'item__position',
        'item__pk'
        'position',
        'value'
    ).select_related('item')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'text': str(e.item) + " – " + str(e),
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@event_permission_required(None)
def category_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    qs = request.event.categories.filter(
        name__icontains=i18ncomp(query)
    ).order_by('name')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'text': str(e),
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

    qf = Q(name__icontains=query)

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
def itemvar_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    pagesize = 20
    offset = (page - 1) * pagesize

    choices = []

    # We are very unlikely to need pagination
    itemqs = request.event.items.prefetch_related('variations').filter(Q(name__icontains=i18ncomp(query)) | Q(internal_name__icontains=query))
    total = itemqs.count()

    for i in itemqs[offset:offset + pagesize]:
        variations = list(i.variations.all())
        if variations:
            choices.append((str(i.pk), _('{product} – Any variation').format(product=i), not i.active))
            for v in variations:
                choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (i, v.value), not v.active))
        else:
            choices.append((str(i.pk), str(i), not i.active))

    doc = {
        'results': [
            {
                'id': k,
                'text': str(v),
            }
            for k, v, d in choices
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
        itemqs = request.event.items.prefetch_related('variations').filter(Q(name__icontains=i18ncomp(query)) | Q(internal_name__icontains=query))
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
            choices.append((str(i.pk), _('{product} – Any variation').format(product=i), '', not i.active))
            for v in variations:
                choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (i, v.value), '', not v.active))
        else:
            choices.append((str(i.pk), str(i), '', not i.active))
    for q in quotaqs:
        if request.event.has_subevents:
            choices.append(('q-%d' % q.pk,
                            _('Any product in quota "{quota}"').format(
                                quota=q
                            ), str(q.subevent), False))
        else:
            choices.append(('q-%d' % q.pk, _('Any product in quota "{quota}"').format(quota=q), '', False))

    doc = {
        'results': [
            {
                'id': k,
                'text': str(v),
                'event': str(t),
                'inactive': d
            }
            for k, v, t, d in choices
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
        if 'can_create' in request.GET:
            qs = qs.filter(pk__in=request.user.teams.filter(can_create_events=True).values_list('organizer', flat=True))
        else:
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


def meta_values(request):
    q = request.GET.get('q')
    propname = request.GET.get('property')
    organizer = request.GET.get('organizer')

    matches = EventMetaValue.objects.filter(
        value__icontains=q,
        property__name=propname
    )
    defaults = EventMetaProperty.objects.filter(
        name=propname,
        default__icontains=q
    )

    if organizer:
        organizer = get_object_or_404(Organizer, slug=organizer)
        if not request.user.has_organizer_permission(organizer, request=request):
            raise PermissionDenied()

        defaults = defaults.filter(organizer_id=organizer.pk)
        matches = matches.filter(event__organizer_id=organizer.pk)
        all_access = (
            (request and request.user.has_active_staff_session(request.session.session_key))
            or request.user.teams.filter(all_events=True, organizer=organizer).exists()
        )
        if not all_access:
            matches = matches.filter(event__id__in=request.user.teams.values_list('limit_events__id', flat=True))

    else:
        # We ignore superuser permissions here. This is intentional – we do not want to show super
        # users a form with all meta properties ever assigned.
        defaults = defaults.filter(
            organizer_id__in=request.user.teams.values_list('organizer', flat=True),
        )

        if not (request and request.user.has_active_staff_session(request.session.session_key)):
            matches = matches.filter(
                Q(event__organizer_id__in=request.user.teams.filter(all_events=True).values_list('organizer', flat=True))
                | Q(event__id__in=request.user.teams.values_list('limit_events__id', flat=True))
            )

    return JsonResponse({
        'results': [
            {'name': v, 'id': v}
            for v in sorted(set(defaults.values_list('default', flat=True)[:10]) | set(matches.values_list('value', flat=True)[:10]))
        ]
    })


def subevent_meta_values(request, organizer, event):
    q = request.GET.get('q')
    propname = request.GET.get('property')

    matches = SubEventMetaValue.objects.filter(
        value__icontains=q,
        property__name=propname,
        subevent__event_id=request.event.pk,
    )
    event_matches = EventMetaValue.objects.filter(
        value__icontains=q,
        property__name=propname,
        event_id=request.event.pk,
    )
    defaults = EventMetaProperty.objects.filter(
        default__icontains=q,
        name=propname,
        organizer_id=request.organizer.pk,
    )

    return JsonResponse({
        'results': [
            {'name': v, 'id': v}
            for v in sorted(
                set(defaults.values_list('default', flat=True)[:10]) |
                set(matches.values_list('value', flat=True)[:10]) |
                set(event_matches.values_list('value', flat=True)[:10])
            )
        ]
    })


def item_meta_values(request, organizer, event):
    q = request.GET.get('q')
    propname = request.GET.get('property')

    matches = ItemMetaValue.objects.filter(
        value__icontains=q,
        property__name=propname
    )
    var_matches = ItemVariationMetaValue.objects.filter(
        value__icontains=q,
        property__name=propname
    )
    defaults = ItemMetaProperty.objects.filter(
        name=propname,
        default__icontains=q
    )

    organizer = get_object_or_404(Organizer, slug=organizer)
    if not request.user.has_organizer_permission(organizer, request=request):
        raise PermissionDenied()

    defaults = defaults.filter(event__organizer_id=organizer.pk)
    matches = matches.filter(item__event__organizer_id=organizer.pk)
    var_matches = var_matches.filter(variation__item__event__organizer_id=organizer.pk)
    all_access = (
        request.user.has_active_staff_session(request.session.session_key)
        or request.user.teams.filter(all_events=True, organizer=organizer, can_change_items=True).exists()
    )
    if not all_access:
        defaults = defaults.filter(
            event__id__in=request.user.teams.filter(can_change_items=True).values_list(
                'limit_events__id', flat=True
            )
        )
        matches = matches.filter(
            item__event__id__in=request.user.teams.filter(can_change_items=True).values_list(
                'limit_events__id', flat=True
            )
        )
        var_matches = var_matches.filter(
            variation__item__event__id__in=request.user.teams.filter(can_change_items=True).values_list(
                'limit_events__id', flat=True
            )
        )

    return JsonResponse({
        'results': [
            {'name': v, 'id': v}
            for v in sorted(
                set(defaults.values_list('default', flat=True)[:10]) |
                set(matches.values_list('value', flat=True)[:10]) |
                set(var_matches.values_list('value', flat=True)[:10])
            )
        ]
    })


@organizer_permission_required(("can_view_orders", "can_change_organizer_settings"))
# This decorator is a bit of a hack since this is not technically an organizer permission, but it does the job here --
# anyone who can see orders for any event can see the check-in log view where this is used as a filter
def devices_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    qq = (
        Q(name__icontains=query) | Q(hardware_brand__icontains=query) | Q(hardware_model__icontains=query) |
        Q(unique_serial__istartswith=query)
    )
    try:
        qq |= Q(device_id=int(query))
    except ValueError:
        pass
    qs = request.organizer.devices.filter(qq).order_by('device_id')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'text': str(e),
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)


@organizer_permission_required(("can_view_orders", "can_change_organizer_settings"))
# This decorator is a bit of a hack since this is not technically an organizer permission, but it does the job here --
# anyone who can see orders for any event can see the check-in log view where this is used as a filter
def gate_select2(request, **kwargs):
    query = request.GET.get('query', '')
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    qs = request.organizer.gates.filter(Q(name__icontains=query) | Q(identifier__icontains=query)).order_by('name')

    total = qs.count()
    pagesize = 20
    offset = (page - 1) * pagesize
    doc = {
        'results': [
            {
                'id': e.pk,
                'text': str(e),
            }
            for e in qs[offset:offset + pagesize]
        ],
        'pagination': {
            "more": total >= (offset + pagesize)
        }
    }
    return JsonResponse(doc)
