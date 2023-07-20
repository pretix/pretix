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
import operator
from functools import reduce

import django_filters
from django.conf import settings
from django.core.exceptions import ValidationError as BaseValidationError
from django.db import transaction
from django.db.models import (
    Count, Exists, F, Max, OrderBy, OuterRef, Prefetch, Q, Subquery,
    prefetch_related_objects,
)
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from packaging.version import parse
from rest_framework import views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.fields import DateTimeField
from rest_framework.generics import ListAPIView
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from pretix.api.serializers.checkin import (
    CheckinListSerializer, CheckinRPCRedeemInputSerializer,
    MiniCheckinListSerializer,
)
from pretix.api.serializers.item import QuestionSerializer
from pretix.api.serializers.order import (
    CheckinListOrderPositionSerializer, FailedCheckinSerializer,
)
from pretix.api.views import RichOrderingFilter
from pretix.api.views.order import OrderPositionFilter
from pretix.base.i18n import language
from pretix.base.models import (
    CachedFile, Checkin, CheckinList, Device, Event, Order, OrderPosition,
    Question, ReusableMedium, RevokedTicketSecret, TeamAPIToken,
)
from pretix.base.services.checkin import (
    CheckInError, RequiredQuestionsError, SQLLogic, perform_checkin,
)

with scopes_disabled():
    class CheckinListFilter(FilterSet):
        subevent_match = django_filters.NumberFilter(method='subevent_match_qs')
        ends_after = django_filters.rest_framework.IsoDateTimeFilter(method='ends_after_qs')

        class Meta:
            model = CheckinList
            fields = ['subevent']

        def subevent_match_qs(self, qs, name, value):
            return qs.filter(
                Q(subevent_id=value) | Q(subevent_id__isnull=True)
            )

        def ends_after_qs(self, queryset, name, value):
            expr = (
                Q(subevent__isnull=True) |
                Q(
                    Q(Q(subevent__date_to__isnull=True) & Q(subevent__date_from__gte=value))
                    | Q(Q(subevent__date_to__isnull=False) & Q(subevent__date_to__gte=value))
                )
            )
            return queryset.filter(expr)


class CheckinListViewSet(viewsets.ModelViewSet):
    serializer_class = CheckinListSerializer
    queryset = CheckinList.objects.none()
    filter_backends = (DjangoFilterBackend, RichOrderingFilter)
    filterset_class = CheckinListFilter
    ordering = ('subevent__date_from', 'name', 'id')
    ordering_fields = ('subevent__date_from', 'id', 'name',)

    def _get_permission_name(self, request):
        if request.path.endswith('/failed_checkins/'):
            return 'can_checkin_orders', 'can_change_orders'
        elif request.method in SAFE_METHODS:
            return 'can_view_orders', 'can_checkin_orders',
        else:
            return 'can_change_event_settings'

    def get_queryset(self):
        qs = self.request.event.checkin_lists.prefetch_related(
            'limit_products',
        )

        if 'subevent' in self.request.query_params.getlist('expand'):
            qs = qs.prefetch_related(
                'subevent', 'subevent__event', 'subevent__subeventitem_set', 'subevent__subeventitemvariation_set',
                'subevent__seat_category_mappings', 'subevent__meta_values'
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.checkinlist.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        return ctx

    def perform_update(self, serializer):
        serializer.save(event=self.request.event)
        serializer.instance.log_action(
            'pretix.event.checkinlist.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )

    def perform_destroy(self, instance):
        instance.log_action(
            'pretix.event.checkinlist.deleted',
            user=self.request.user,
            auth=self.request.auth,
        )
        super().perform_destroy(instance)

    @action(detail=True, methods=['POST'], url_name='failed_checkins')
    @transaction.atomic()
    def failed_checkins(self, *args, **kwargs):
        serializer = FailedCheckinSerializer(
            data=self.request.data,
            context={'event': self.request.event}
        )
        serializer.is_valid(raise_exception=True)
        kwargs = {}

        if not serializer.validated_data.get('position'):
            kwargs['position'] = OrderPosition.all.filter(
                secret=serializer.validated_data['raw_barcode']
            ).first()

        c = serializer.save(
            list=self.get_object(),
            successful=False,
            forced=True,
            force_sent=True,
            device=self.request.auth if isinstance(self.request.auth, Device) else None,
            gate=self.request.auth.gate if isinstance(self.request.auth, Device) else None,
            **kwargs,
        )
        if c.position:
            c.position.order.log_action('pretix.event.checkin.denied', data={
                'position': c.position.id,
                'positionid': c.position.positionid,
                'errorcode': c.error_reason,
                'reason_explanation': c.error_explanation,
                'datetime': c.datetime,
                'type': c.type,
                'list': c.list.pk
            }, user=self.request.user, auth=self.request.auth)
        else:
            self.request.event.log_action('pretix.event.checkin.unknown', data={
                'datetime': c.datetime,
                'type': c.type,
                'list': c.list.pk,
                'barcode': c.raw_barcode
            }, user=self.request.user, auth=self.request.auth)

        return Response(serializer.data, status=201)

    @action(detail=True, methods=['GET'])
    def status(self, *args, **kwargs):
        with language(self.request.event.settings.locale):
            clist = self.get_object()
            cqs = clist.positions.annotate(
                checkedin=Exists(Checkin.objects.filter(list_id=clist.pk, position=OuterRef('pk'), type=Checkin.TYPE_ENTRY))
            ).filter(
                checkedin=True,
            )
            pqs = clist.positions

            ev = clist.subevent or clist.event
            response = {
                'event': {
                    'name': str(ev.name),
                },
                'checkin_count': cqs.count(),
                'position_count': pqs.count(),
                'inside_count': clist.inside_count,
            }

            op_by_item = {
                p['item']: p['cnt']
                for p in pqs.order_by().values('item').annotate(cnt=Count('id'))
            }
            op_by_variation = {
                p['variation']: p['cnt']
                for p in pqs.order_by().values('variation').annotate(cnt=Count('id'))
            }
            c_by_item = {
                p['item']: p['cnt']
                for p in cqs.order_by().values('item').annotate(cnt=Count('id'))
            }
            c_by_variation = {
                p['variation']: p['cnt']
                for p in cqs.order_by().values('variation').annotate(cnt=Count('id'))
            }

            if not clist.all_products:
                items = clist.limit_products
            else:
                items = clist.event.items

            response['items'] = []
            for item in items.order_by('category__position', 'position', 'pk').prefetch_related('variations'):
                i = {
                    'id': item.pk,
                    'name': str(item),
                    'admission': item.admission,
                    'checkin_count': c_by_item.get(item.pk, 0),
                    'position_count': op_by_item.get(item.pk, 0),
                    'variations': []
                }
                for var in item.variations.all():
                    i['variations'].append({
                        'id': var.pk,
                        'value': str(var),
                        'checkin_count': c_by_variation.get(var.pk, 0),
                        'position_count': op_by_variation.get(var.pk, 0),
                    })
                response['items'].append(i)

            return Response(response)


with scopes_disabled():
    class CheckinOrderPositionFilter(OrderPositionFilter):
        check_rules = django_filters.rest_framework.BooleanFilter(method='check_rules_qs')
        # check_rules is currently undocumented on purpose, let's get a feel for the performance impact first

        def __init__(self, *args, **kwargs):
            self.checkinlist = kwargs.pop('checkinlist')
            super().__init__(*args, **kwargs)

        def has_checkin_qs(self, queryset, name, value):
            return queryset.filter(last_checked_in__isnull=not value)

        def check_rules_qs(self, queryset, name, value):
            if not self.checkinlist.rules:
                return queryset
            return queryset.filter(
                SQLLogic(self.checkinlist).apply(self.checkinlist.rules)
            ).filter(
                Q(valid_from__isnull=True) | Q(valid_from__lte=now()),
                Q(valid_until__isnull=True) | Q(valid_until__gte=now()),
                blocked__isnull=True,
            )


def _handle_file_upload(data, user, auth):
    try:
        cf = CachedFile.objects.get(
            session_key=f'api-upload-{str(type(user or auth))}-{(user or auth).pk}',
            file__isnull=False,
            pk=data[len("file:"):],
        )
    except (ValidationError, BaseValidationError, IndexError):  # invalid uuid
        raise ValidationError('The submitted file ID "{fid}" was not found.'.format(fid=data))
    except CachedFile.DoesNotExist:
        raise ValidationError('The submitted file ID "{fid}" was not found.'.format(fid=data))

    allowed_types = (
        'image/png', 'image/jpeg', 'image/gif', 'application/pdf'
    )
    if cf.type not in allowed_types:
        raise ValidationError('The submitted file "{fid}" has a file type that is not allowed in this field.'.format(fid=data))
    if cf.file.size > settings.FILE_UPLOAD_MAX_SIZE_OTHER:
        raise ValidationError('The submitted file "{fid}" is too large to be used in this field.'.format(fid=data))

    return cf.file


def _checkin_list_position_queryset(checkinlists, ignore_status=False, ignore_products=False, pdf_data=False, expand=None):
    list_by_event = {cl.event_id: cl for cl in checkinlists}
    if not checkinlists:
        raise ValidationError('No check-in list passed.')
    if len(list_by_event) != len(checkinlists):
        raise ValidationError('Selecting two check-in lists from the same event is unsupported.')

    cqs = Checkin.objects.filter(
        position_id=OuterRef('pk'),
        list_id__in=[cl.pk for cl in checkinlists]
    ).order_by().values('position_id').annotate(
        m=Max('datetime')
    ).values('m')

    qs = OrderPosition.objects.filter(
        order__event__in=list_by_event.keys(),
    ).annotate(
        last_checked_in=Subquery(cqs)
    ).prefetch_related('order__event', 'order__event__organizer')

    lists_qs = []
    for checkinlist in checkinlists:
        list_q = Q(order__event_id=checkinlist.event_id)
        if checkinlist.subevent:
            list_q &= Q(subevent=checkinlist.subevent)
        if not ignore_status:
            if checkinlist.include_pending:
                list_q &= Q(order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING])
            else:
                list_q &= Q(
                    Q(order__status=Order.STATUS_PAID) |
                    Q(order__status=Order.STATUS_PENDING, order__valid_if_pending=True)
                )
        if not checkinlist.all_products and not ignore_products:
            list_q &= Q(item__in=checkinlist.limit_products.values_list('id', flat=True))
        lists_qs.append(list_q)

    qs = qs.filter(reduce(operator.or_, lists_qs))

    if pdf_data:
        qs = qs.prefetch_related(
            Prefetch(
                lookup='checkins',
                queryset=Checkin.objects.filter(list_id__in=[cl.pk for cl in checkinlists])
            ),
            'answers', 'answers__options', 'answers__question',
            Prefetch('addons', OrderPosition.objects.select_related('item', 'variation')),
            Prefetch('order', Order.objects.select_related('invoice_address').prefetch_related(
                Prefetch(
                    'event',
                    Event.objects.select_related('organizer')
                ),
                Prefetch(
                    'positions',
                    OrderPosition.objects.prefetch_related(
                        Prefetch('checkins', queryset=Checkin.objects.all()),
                        'item', 'variation', 'answers', 'answers__options', 'answers__question',
                    )
                )
            ))
        ).select_related(
            'item', 'variation', 'item__category', 'addon_to', 'order', 'order__invoice_address', 'seat'
        )
    else:
        qs = qs.prefetch_related(
            Prefetch(
                lookup='checkins',
                queryset=Checkin.objects.filter(list_id__in=[cl.pk for cl in checkinlists])
            ),
            'answers', 'answers__options', 'answers__question',
            Prefetch('addons', OrderPosition.objects.select_related('item', 'variation'))
        ).select_related('item', 'variation', 'order', 'addon_to', 'order__invoice_address', 'order', 'seat')

    if expand and 'subevent' in expand:
        qs = qs.prefetch_related(
            'subevent', 'subevent__event', 'subevent__subeventitem_set', 'subevent__subeventitemvariation_set',
            'subevent__seat_category_mappings', 'subevent__meta_values'
        )

    if expand and 'item' in expand:
        qs = qs.prefetch_related('item', 'item__addons', 'item__bundles', 'item__meta_values',
                                 'item__variations').select_related('item__tax_rule')

    if expand and 'variation' in expand:
        qs = qs.prefetch_related('variation')

    return qs


def _redeem_process(*, checkinlists, raw_barcode, answers_data, datetime, force, checkin_type, ignore_unpaid, nonce,
                    untrusted_input, user, auth, expand, pdf_data, request, questions_supported, canceled_supported,
                    source_type='barcode', legacy_url_support=False, simulate=False):
    if not checkinlists:
        raise ValidationError('No check-in list passed.')

    list_by_event = {cl.event_id: cl for cl in checkinlists}
    prefetch_related_objects([cl for cl in checkinlists if not cl.all_products], 'limit_products')

    device = auth if isinstance(auth, Device) else None
    gate = auth.gate if isinstance(auth, Device) else None

    context = {
        'request': request,
        'expand': expand,
    }

    def _make_context(context, event):
        return {
            **context,
            'event': op.order.event,
            'pdf_data': pdf_data and (
                user if user and user.is_authenticated else auth
            ).has_event_permission(request.organizer, event, 'can_view_orders', request),
        }

    common_checkin_args = dict(
        raw_barcode=raw_barcode,
        raw_source_type=source_type,
        type=checkin_type,
        list=checkinlists[0],
        datetime=datetime,
        device=device,
        gate=gate,
        nonce=nonce,
        forced=force,
    )
    raw_barcode_for_checkin = None
    from_revoked_secret = False
    if simulate:
        common_checkin_args['__fake_arg_to_prevent_this_from_being_saved'] = True

    # 1. Gather a list of positions that could be the one we looking for, either from their ID, secret or
    #    parent secret
    queryset = _checkin_list_position_queryset(checkinlists, pdf_data=pdf_data, ignore_status=True, ignore_products=True).order_by(
        F('addon_to').asc(nulls_first=True)
    )

    q = Q(secret=raw_barcode)
    if any(cl.addon_match for cl in checkinlists):
        q |= Q(addon_to__secret=raw_barcode)
    if raw_barcode.isnumeric() and not untrusted_input and legacy_url_support:
        q |= Q(pk=raw_barcode)

    op_candidates = list(queryset.filter(q))
    if not op_candidates and '+' in raw_barcode and legacy_url_support:
        # In application/x-www-form-urlencoded, you can encodes space ' ' with '+' instead of '%20'.
        # `id`, however, is part of a path where this technically is not allowed. Old versions of our
        # scan apps still do it, so we try work around it!
        q = Q(secret=raw_barcode.replace('+', ' '))
        if any(cl.addon_match for cl in checkinlists):
            q |= Q(addon_to__secret=raw_barcode.replace('+', ' '))
        op_candidates = list(queryset.filter(q))

    # 2. Handle the "nothing found" case: Either it's really a bogus secret that we don't know (-> error), or it
    #    might be a revoked one that we actually know (-> error, but with better error message and logging and
    #    with respecting the force option), or it's a reusable medium (-> proceed with that)
    if not op_candidates:
        try:
            media = ReusableMedium.objects.select_related('linked_orderposition').active().get(
                organizer_id=checkinlists[0].event.organizer_id,
                type=source_type,
                identifier=raw_barcode,
                linked_orderposition__isnull=False,
            )
            raw_barcode_for_checkin = raw_barcode
        except ReusableMedium.DoesNotExist:
            revoked_matches = list(
                RevokedTicketSecret.objects.filter(event_id__in=list_by_event.keys(), secret=raw_barcode))
            if len(revoked_matches) == 0:
                if not simulate:
                    checkinlists[0].event.log_action('pretix.event.checkin.unknown', data={
                        'datetime': datetime,
                        'type': checkin_type,
                        'list': checkinlists[0].pk,
                        'barcode': raw_barcode,
                        'searched_lists': [cl.pk for cl in checkinlists]
                    }, user=user, auth=auth)

                for cl in checkinlists:
                    for k, s in cl.event.ticket_secret_generators.items():
                        try:
                            parsed = s.parse_secret(raw_barcode)
                            common_checkin_args.update({
                                'raw_item': parsed.item,
                                'raw_variation': parsed.variation,
                                'raw_subevent': parsed.subevent,
                            })
                        except:
                            pass

                if not simulate:
                    Checkin.objects.create(
                        position=None,
                        successful=False,
                        error_reason=Checkin.REASON_INVALID,
                        **common_checkin_args,
                    )

                if force and legacy_url_support and isinstance(auth, Device):
                    # There was a bug in libpretixsync: If you scanned a ticket in offline mode that was
                    # valid at the time but no longer exists at time of upload, the device would retry to
                    # upload the same scan over and over again. Since we can't update all devices quickly,
                    # here's a dirty workaround to make it stop.
                    try:
                        brand = auth.software_brand
                        ver = parse(auth.software_version)
                        legacy_mode = (
                            (brand == 'pretixSCANPROXY' and ver < parse('0.0.3')) or
                            (brand == 'pretixSCAN Android' and ver < parse('1.11.2')) or
                            (brand == 'pretixSCAN' and ver < parse('1.11.2'))
                        )
                        if legacy_mode:
                            return Response({
                                'status': 'error',
                                'reason': Checkin.REASON_ALREADY_REDEEMED,
                                'reason_explanation': None,
                                'require_attention': False,
                                '__warning': 'Compatibility hack active due to detected old pretixSCAN version',
                            }, status=400)
                    except:  # we don't care e.g. about invalid version numbers
                        pass

                return Response({
                    'detail': 'Not found.',  # for backwards compatibility
                    'status': 'error',
                    'reason': Checkin.REASON_INVALID,
                    'reason_explanation': None,
                    'require_attention': False,
                    'list': MiniCheckinListSerializer(checkinlists[0]).data,
                }, status=404)
            elif revoked_matches and force:
                op_candidates = [revoked_matches[0].position]
                if list_by_event[revoked_matches[0].event_id].addon_match:
                    op_candidates += list(revoked_matches[0].position.addons.all())
                raw_barcode_for_checkin = raw_barcode_for_checkin or raw_barcode
                from_revoked_secret = True
            else:
                op = revoked_matches[0].position
                if not simulate:
                    op.order.log_action('pretix.event.checkin.revoked', data={
                        'datetime': datetime,
                        'type': checkin_type,
                        'list': list_by_event[revoked_matches[0].event_id].pk,
                        'barcode': raw_barcode
                    }, user=user, auth=auth)
                    common_checkin_args['list'] = list_by_event[revoked_matches[0].event_id]
                    Checkin.objects.create(
                        position=op,
                        successful=False,
                        error_reason=Checkin.REASON_REVOKED,
                        **common_checkin_args
                    )
                return Response({
                    'status': 'error',
                    'reason': Checkin.REASON_REVOKED,
                    'reason_explanation': None,
                    'require_attention': False,
                    'position': CheckinListOrderPositionSerializer(op, context=_make_context(context, revoked_matches[
                        0].event)).data,
                    'list': MiniCheckinListSerializer(list_by_event[revoked_matches[0].event_id]).data,
                }, status=400)
        else:
            op_candidates = [media.linked_orderposition]
            if list_by_event[media.linked_orderposition.order.event_id].addon_match:
                op_candidates += list(media.linked_orderposition.addons.all())

    # 3. Handle the "multiple options found" case: Except for the unlikely case of a secret being also a valid primary
    #    key on the same list, we're probably dealing with the ``addon_match`` case here and need to figure out
    #    which add-on has the right product.
    if len(op_candidates) > 1:
        op_candidates_matching_product = [
            op for op in op_candidates
            if (
                (list_by_event[op.order.event_id].addon_match or op.secret == raw_barcode or legacy_url_support) and
                (list_by_event[op.order.event_id].all_products or op.item_id in {i.pk for i in list_by_event[op.order.event_id].limit_products.all()})
            )
        ]

        if len(op_candidates_matching_product) == 0:
            # None of the found add-ons has the correct product, too bad! We could just error out here, but
            # instead we just continue with *any* product and have it rejected by the check in perform_checkin.
            # This has the advantage of a better error message.
            op_candidates = [op_candidates[0]]
        elif len(op_candidates_matching_product) > 1:
            # It's still ambiguous, we'll error out.
            # We choose the first match (regardless of product) for the logging since it's most likely to be the
            # base product according to our order_by above.
            op = op_candidates[0]
            if not simulate:
                op.order.log_action('pretix.event.checkin.denied', data={
                    'position': op.id,
                    'positionid': op.positionid,
                    'errorcode': Checkin.REASON_AMBIGUOUS,
                    'reason_explanation': None,
                    'force': force,
                    'datetime': datetime,
                    'type': checkin_type,
                    'list': list_by_event[op.order.event_id].pk,
                }, user=user, auth=auth)
                common_checkin_args['list'] = list_by_event[op.order.event_id]
                Checkin.objects.create(
                    position=op,
                    successful=False,
                    error_reason=Checkin.REASON_AMBIGUOUS,
                    error_explanation=None,
                    **common_checkin_args,
                )
            return Response({
                'status': 'error',
                'reason': Checkin.REASON_AMBIGUOUS,
                'reason_explanation': None,
                'require_attention': op.require_checkin_attention,
                'position': CheckinListOrderPositionSerializer(op, context=_make_context(context, op.order.event)).data,
                'list': MiniCheckinListSerializer(list_by_event[op.order.event_id]).data,
            }, status=400)
        else:
            op_candidates = op_candidates_matching_product

    op = op_candidates[0]
    common_checkin_args['list'] = list_by_event[op.order.event_id]

    # 5. Pre-validate all incoming answers, handle file upload
    given_answers = {}
    if answers_data:
        for q in op.item.questions.filter(ask_during_checkin=True):
            if str(q.pk) in answers_data:
                try:
                    if q.type == Question.TYPE_FILE:
                        given_answers[q] = _handle_file_upload(answers_data[str(q.pk)], user, auth)
                    else:
                        given_answers[q] = q.clean_answer(answers_data[str(q.pk)])
                except (ValidationError, BaseValidationError):
                    pass

    # 6. Pass to our actual check-in logic
    with language(op.order.event.settings.locale):
        try:
            perform_checkin(
                op=op,
                clist=list_by_event[op.order.event_id],
                given_answers=given_answers,
                force=force,
                ignore_unpaid=ignore_unpaid,
                nonce=nonce,
                datetime=datetime,
                questions_supported=questions_supported,
                canceled_supported=canceled_supported,
                user=user,
                auth=auth,
                type=checkin_type,
                raw_barcode=raw_barcode_for_checkin,
                raw_source_type=source_type,
                from_revoked_secret=from_revoked_secret,
                simulate=simulate,
            )
        except RequiredQuestionsError as e:
            return Response({
                'status': 'incomplete',
                'require_attention': op.require_checkin_attention,
                'position': CheckinListOrderPositionSerializer(op, context=_make_context(context, op.order.event)).data,
                'questions': [
                    QuestionSerializer(q).data for q in e.questions
                ],
                'list': MiniCheckinListSerializer(list_by_event[op.order.event_id]).data,
            }, status=400)
        except CheckInError as e:
            if not simulate:
                op.order.log_action('pretix.event.checkin.denied', data={
                    'position': op.id,
                    'positionid': op.positionid,
                    'errorcode': e.code,
                    'reason_explanation': e.reason,
                    'force': force,
                    'datetime': datetime,
                    'type': checkin_type,
                    'list': list_by_event[op.order.event_id].pk,
                }, user=user, auth=auth)
                Checkin.objects.create(
                    position=op,
                    successful=False,
                    error_reason=e.code,
                    error_explanation=e.reason,
                    **common_checkin_args,
                )
            return Response({
                'status': 'error',
                'reason': e.code,
                'reason_explanation': e.reason,
                'require_attention': op.require_checkin_attention,
                'position': CheckinListOrderPositionSerializer(op, context=_make_context(context, op.order.event)).data,
                'list': MiniCheckinListSerializer(list_by_event[op.order.event_id]).data,
            }, status=400)
        else:
            return Response({
                'status': 'ok',
                'require_attention': op.require_checkin_attention,
                'position': CheckinListOrderPositionSerializer(op, context=_make_context(context, op.order.event)).data,
                'list': MiniCheckinListSerializer(list_by_event[op.order.event_id]).data,
            }, status=201)


class ExtendedBackend(DjangoFilterBackend):
    def get_filterset_kwargs(self, request, queryset, view):
        kwargs = super().get_filterset_kwargs(request, queryset, view)

        # merge filterset kwargs provided by view class
        if hasattr(view, 'get_filterset_kwargs'):
            kwargs.update(view.get_filterset_kwargs())

        return kwargs


class CheckinListPositionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CheckinListOrderPositionSerializer
    queryset = OrderPosition.all.none()
    filter_backends = (ExtendedBackend, RichOrderingFilter)
    ordering = (F('attendee_name_cached').asc(nulls_last=True), 'pk')
    ordering_fields = (
        'order__code', 'order__datetime', 'positionid', 'attendee_name',
        'last_checked_in', 'order__email',
    )
    ordering_custom = {
        'attendee_name': {
            '_order': F('display_name').asc(nulls_first=True),
            'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')
        },
        '-attendee_name': {
            '_order': F('display_name').desc(nulls_last=True),
            'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')
        },
        'last_checked_in': {
            '_order': OrderBy(F('last_checked_in'), nulls_first=True),
        },
        '-last_checked_in': {
            '_order': OrderBy(F('last_checked_in'), nulls_last=True, descending=True),
        },
    }

    filterset_class = CheckinOrderPositionFilter
    permission = ('can_view_orders', 'can_checkin_orders')
    write_permission = ('can_change_orders', 'can_checkin_orders')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self.request.event
        ctx['expand'] = self.request.query_params.getlist('expand')
        ctx['pdf_data'] = self.request.query_params.get('pdf_data', 'false') == 'true'
        return ctx

    def get_filterset_kwargs(self):
        return {
            'checkinlist': self.checkinlist,
        }

    @cached_property
    def checkinlist(self):
        try:
            return get_object_or_404(self.request.event.checkin_lists, pk=self.kwargs.get("list"))
        except ValueError:
            raise Http404()

    def get_queryset(self, ignore_status=False, ignore_products=False):
        qs = _checkin_list_position_queryset(
            [self.checkinlist],
            ignore_status=self.request.query_params.get('ignore_status', 'false') == 'true' or ignore_status,
            ignore_products=ignore_products,
            pdf_data=self.request.query_params.get('pdf_data', 'false') == 'true',
            expand=self.request.query_params.getlist('expand'),
        )

        if 'pk' not in self.request.resolver_match.kwargs and 'can_view_orders' not in self.request.eventpermset \
                and len(self.request.query_params.get('search', '')) < 3:
            qs = qs.none()

        return qs

    @action(detail=False, methods=['POST'], url_name='redeem', url_path='(?P<pk>.*)/redeem')
    def redeem(self, *args, **kwargs):
        force = bool(self.request.data.get('force', False))
        checkin_type = self.request.data.get('type', None) or Checkin.TYPE_ENTRY
        if checkin_type not in dict(Checkin.CHECKIN_TYPES):
            raise ValidationError("Invalid check-in type.")
        ignore_unpaid = bool(self.request.data.get('ignore_unpaid', False))
        nonce = self.request.data.get('nonce')
        untrusted_input = (
            self.request.GET.get('untrusted_input', '') not in ('0', 'false', 'False', '')
            or (isinstance(self.request.auth, Device) and 'pretixscan' in (self.request.auth.software_brand or '').lower())
        )

        if 'datetime' in self.request.data:
            dt = DateTimeField().to_internal_value(self.request.data.get('datetime'))
        else:
            dt = now()

        answers_data = self.request.data.get('answers')
        return _redeem_process(
            checkinlists=[self.checkinlist],
            raw_barcode=kwargs['pk'],
            answers_data=answers_data,
            datetime=dt,
            force=force,
            checkin_type=checkin_type,
            ignore_unpaid=ignore_unpaid,
            nonce=nonce,
            untrusted_input=untrusted_input,
            user=self.request.user,
            auth=self.request.auth,
            expand=self.request.query_params.getlist('expand'),
            pdf_data=self.request.query_params.get('pdf_data', 'false') == 'true',
            questions_supported=self.request.data.get('questions_supported', True),
            canceled_supported=self.request.data.get('canceled_supported', False),
            request=self.request,  # this is not clean, but we need it in the serializers for URL generation
            legacy_url_support=True,
        )


class CheckinRPCRedeemView(views.APIView):
    def post(self, request, *args, **kwargs):
        if isinstance(self.request.auth, (TeamAPIToken, Device)):
            events = self.request.auth.get_events_with_permission(('can_change_orders', 'can_checkin_orders'))
        elif self.request.user.is_authenticated:
            events = self.request.user.get_events_with_permission(('can_change_orders', 'can_checkin_orders'), self.request).filter(
                organizer=self.request.organizer
            )
        else:
            raise ValueError("unknown authentication method")

        s = CheckinRPCRedeemInputSerializer(data=request.data, context={'events': events})
        s.is_valid(raise_exception=True)
        return _redeem_process(
            checkinlists=s.validated_data['lists'],
            raw_barcode=s.validated_data['secret'],
            source_type=s.validated_data['source_type'],
            answers_data=s.validated_data.get('answers'),
            datetime=s.validated_data.get('datetime') or now(),
            force=s.validated_data['force'],
            checkin_type=s.validated_data['type'],
            ignore_unpaid=s.validated_data['ignore_unpaid'],
            nonce=s.validated_data.get('nonce'),
            untrusted_input=True,
            user=self.request.user,
            auth=self.request.auth,
            expand=self.request.query_params.getlist('expand'),
            pdf_data=self.request.query_params.get('pdf_data', 'false') == 'true',
            questions_supported=s.validated_data['questions_supported'],
            canceled_supported=True,
            request=self.request,  # this is not clean, but we need it in the serializers for URL generation
            legacy_url_support=False,
        )


class CheckinRPCSearchView(ListAPIView):
    serializer_class = CheckinListOrderPositionSerializer
    queryset = OrderPosition.all.none()
    filter_backends = (ExtendedBackend, RichOrderingFilter)
    ordering = (F('attendee_name_cached').asc(nulls_last=True), 'positionid')
    ordering_fields = (
        'order__code', 'order__datetime', 'positionid', 'attendee_name',
        'last_checked_in', 'order__email',
    )
    ordering_custom = {
        'attendee_name': {
            '_order': F('display_name').asc(nulls_first=True),
            'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')
        },
        '-attendee_name': {
            '_order': F('display_name').desc(nulls_last=True),
            'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')
        },
        'last_checked_in': {
            '_order': OrderBy(F('last_checked_in'), nulls_first=True),
        },
        '-last_checked_in': {
            '_order': OrderBy(F('last_checked_in'), nulls_last=True, descending=True),
        },
    }
    filterset_class = OrderPositionFilter

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['expand'] = self.request.query_params.getlist('expand')
        ctx['pdf_data'] = False
        return ctx

    @cached_property
    def lists(self):
        if isinstance(self.request.auth, (TeamAPIToken, Device)):
            events = self.request.auth.get_events_with_permission(('can_view_orders', 'can_checkin_orders'))
        elif self.request.user.is_authenticated:
            events = self.request.user.get_events_with_permission(('can_view_orders', 'can_checkin_orders'), self.request).filter(
                organizer=self.request.organizer
            )
        else:
            raise ValueError("unknown authentication method")
        requested_lists = [int(l) for l in self.request.query_params.getlist('list') if l.isdigit()]
        lists = list(
            CheckinList.objects.filter(event__in=events).select_related('event').filter(id__in=requested_lists)
        )
        if len(lists) != len(requested_lists):
            missing_lists = set(requested_lists) - {l.pk for l in lists}
            raise PermissionDenied("You requested lists that do not exist or that you do not have access to: " + ", ".join(str(l) for l in missing_lists))
        return lists

    @cached_property
    def has_full_access_permission(self):
        if isinstance(self.request.auth, (TeamAPIToken, Device)):
            events = self.request.auth.get_events_with_permission('can_view_orders')
        elif self.request.user.is_authenticated:
            events = self.request.user.get_events_with_permission('can_view_orders', self.request).filter(
                organizer=self.request.organizer
            )
        else:
            raise ValueError("unknown authentication method")

        full_access_lists = CheckinList.objects.filter(event__in=events).filter(id__in=[c.pk for c in self.lists]).count()
        return len(self.lists) == full_access_lists

    def get_queryset(self, ignore_status=False, ignore_products=False):
        qs = _checkin_list_position_queryset(
            self.lists,
            ignore_status=self.request.query_params.get('ignore_status', 'false') == 'true' or ignore_status,
            ignore_products=ignore_products,
            pdf_data=self.request.query_params.get('pdf_data', 'false') == 'true',
            expand=self.request.query_params.getlist('expand'),
        )

        if len(self.request.query_params.get('search', '')) < 3 and not self.has_full_access_permission:
            qs = qs.none()

        return qs
