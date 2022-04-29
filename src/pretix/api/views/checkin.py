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
import django_filters
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import (
    Count, Exists, F, Max, OrderBy, OuterRef, Prefetch, Q, Subquery,
)
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from packaging.version import parse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.fields import DateTimeField
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from pretix.api.serializers.checkin import CheckinListSerializer
from pretix.api.serializers.item import QuestionSerializer
from pretix.api.serializers.order import (
    CheckinListOrderPositionSerializer, FailedCheckinSerializer,
)
from pretix.api.views import RichOrderingFilter
from pretix.api.views.order import OrderPositionFilter
from pretix.base.i18n import language
from pretix.base.models import (
    CachedFile, Checkin, CheckinList, Device, Event, Order, OrderPosition,
    Question,
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
    filter_backends = (DjangoFilterBackend,)
    filterset_class = CheckinListFilter

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
            return queryset.filter(SQLLogic(self.checkinlist).apply(self.checkinlist.rules))


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
    ordering = ('attendee_name_cached', 'positionid')
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
        return ctx

    def get_filterset_kwargs(self):
        return {
            'checkinlist': self.checkinlist,
        }

    @cached_property
    def checkinlist(self):
        try:
            return get_object_or_404(CheckinList, event=self.request.event, pk=self.kwargs.get("list"))
        except ValueError:
            raise Http404()

    def get_queryset(self, ignore_status=False, ignore_products=False):
        cqs = Checkin.objects.filter(
            position_id=OuterRef('pk'),
            list_id=self.checkinlist.pk
        ).order_by().values('position_id').annotate(
            m=Max('datetime')
        ).values('m')

        qs = OrderPosition.objects.filter(
            order__event=self.request.event,
        ).annotate(
            last_checked_in=Subquery(cqs)
        ).prefetch_related('order__event', 'order__event__organizer')
        if self.checkinlist.subevent:
            qs = qs.filter(
                subevent=self.checkinlist.subevent
            )

        if self.request.query_params.get('ignore_status', 'false') != 'true' and not ignore_status:
            qs = qs.filter(
                order__status__in=[Order.STATUS_PAID, Order.STATUS_PENDING] if self.checkinlist.include_pending else [Order.STATUS_PAID]
            )
        if self.request.query_params.get('pdf_data', 'false') == 'true':
            qs = qs.prefetch_related(
                Prefetch(
                    lookup='checkins',
                    queryset=Checkin.objects.filter(list_id=self.checkinlist.pk)
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
                    queryset=Checkin.objects.filter(list_id=self.checkinlist.pk)
                ),
                'answers', 'answers__options', 'answers__question',
                Prefetch('addons', OrderPosition.objects.select_related('item', 'variation'))
            ).select_related('item', 'variation', 'order', 'addon_to', 'order__invoice_address', 'order', 'seat')

        if not self.checkinlist.all_products and not ignore_products:
            qs = qs.filter(item__in=self.checkinlist.limit_products.values_list('id', flat=True))

        if 'subevent' in self.request.query_params.getlist('expand'):
            qs = qs.prefetch_related(
                'subevent', 'subevent__event', 'subevent__subeventitem_set', 'subevent__subeventitemvariation_set',
                'subevent__seat_category_mappings', 'subevent__meta_values'
            )

        if 'item' in self.request.query_params.getlist('expand'):
            qs = qs.prefetch_related('item', 'item__addons', 'item__bundles', 'item__meta_values', 'item__variations').select_related('item__tax_rule')

        if 'variation' in self.request.query_params.getlist('expand'):
            qs = qs.prefetch_related('variation')

        if 'pk' not in self.request.resolver_match.kwargs and 'can_view_orders' not in self.request.eventpermset \
                and len(self.request.query_params.get('search', '')) < 3:
            qs = qs.none()

        return qs

    @action(detail=False, methods=['POST'], url_name='redeem', url_path='(?P<pk>.*)/redeem')
    def redeem(self, *args, **kwargs):
        force = bool(self.request.data.get('force', False))
        type = self.request.data.get('type', None) or Checkin.TYPE_ENTRY
        if type not in dict(Checkin.CHECKIN_TYPES):
            raise ValidationError("Invalid check-in type.")
        ignore_unpaid = bool(self.request.data.get('ignore_unpaid', False))
        nonce = self.request.data.get('nonce')

        if 'datetime' in self.request.data:
            dt = DateTimeField().to_internal_value(self.request.data.get('datetime'))
        else:
            dt = now()

        common_checkin_args = dict(
            raw_barcode=self.kwargs['pk'],
            type=type,
            list=self.checkinlist,
            datetime=dt,
            device=self.request.auth if isinstance(self.request.auth, Device) else None,
            gate=self.request.auth.gate if isinstance(self.request.auth, Device) else None,
            nonce=nonce,
            forced=force,
        )
        raw_barcode_for_checkin = None
        from_revoked_secret = False

        try:
            queryset = self.get_queryset(ignore_status=True, ignore_products=True)
            if self.kwargs['pk'].isnumeric():
                op = queryset.get(Q(pk=self.kwargs['pk']) | Q(secret=self.kwargs['pk']))
            else:
                # In application/x-www-form-urlencoded, you can encodes space ' ' with '+' instead of '%20'.
                # `id`, however, is part of a path where this technically is not allowed. Old versions of our
                # scan apps still do it, so we try work around it!
                try:
                    op = queryset.get(secret=self.kwargs['pk'])
                except OrderPosition.DoesNotExist:
                    op = queryset.get(secret=self.kwargs['pk'].replace('+', ' '))
        except OrderPosition.DoesNotExist:
            revoked_matches = list(self.request.event.revoked_secrets.filter(secret=self.kwargs['pk']))
            if len(revoked_matches) == 0:
                self.request.event.log_action('pretix.event.checkin.unknown', data={
                    'datetime': dt,
                    'type': type,
                    'list': self.checkinlist.pk,
                    'barcode': self.kwargs['pk']
                }, user=self.request.user, auth=self.request.auth)

                for k, s in self.request.event.ticket_secret_generators.items():
                    try:
                        parsed = s.parse_secret(self.kwargs['pk'])
                        common_checkin_args.update({
                            'raw_item': parsed.item,
                            'raw_variation': parsed.variation,
                            'raw_subevent': parsed.subevent,
                        })
                    except:
                        pass

                Checkin.objects.create(
                    position=None,
                    successful=False,
                    error_reason=Checkin.REASON_INVALID,
                    **common_checkin_args,
                )

                if force and isinstance(self.request.auth, Device):
                    # There was a bug in libpretixsync: If you scanned a ticket in offline mode that was
                    # valid at the time but no longer exists at time of upload, the device would retry to
                    # upload the same scan over and over again. Since we can't update all devices quickly,
                    # here's a dirty workaround to make it stop.
                    try:
                        brand = self.request.auth.software_brand
                        ver = parse(self.request.auth.software_version)
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
                }, status=404)
            elif revoked_matches and force:
                op = revoked_matches[0].position
                raw_barcode_for_checkin = self.kwargs['pk']
                from_revoked_secret = True
            else:
                op = revoked_matches[0].position
                op.order.log_action('pretix.event.checkin.revoked', data={
                    'datetime': dt,
                    'type': type,
                    'list': self.checkinlist.pk,
                    'barcode': self.kwargs['pk']
                }, user=self.request.user, auth=self.request.auth)
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
                    'position': CheckinListOrderPositionSerializer(op, context=self.get_serializer_context()).data
                }, status=400)

        given_answers = {}
        if 'answers' in self.request.data:
            aws = self.request.data.get('answers')
            for q in op.item.questions.filter(ask_during_checkin=True):
                if str(q.pk) in aws:
                    try:
                        if q.type == Question.TYPE_FILE:
                            given_answers[q] = self._handle_file_upload(aws[str(q.pk)])
                        else:
                            given_answers[q] = q.clean_answer(aws[str(q.pk)])
                    except ValidationError:
                        pass

        with language(self.request.event.settings.locale):
            try:
                perform_checkin(
                    op=op,
                    clist=self.checkinlist,
                    given_answers=given_answers,
                    force=force,
                    ignore_unpaid=ignore_unpaid,
                    nonce=nonce,
                    datetime=dt,
                    questions_supported=self.request.data.get('questions_supported', True),
                    canceled_supported=self.request.data.get('canceled_supported', False),
                    user=self.request.user,
                    auth=self.request.auth,
                    type=type,
                    raw_barcode=raw_barcode_for_checkin,
                    from_revoked_secret=from_revoked_secret,
                )
            except RequiredQuestionsError as e:
                return Response({
                    'status': 'incomplete',
                    'require_attention': op.item.checkin_attention or op.order.checkin_attention,
                    'position': CheckinListOrderPositionSerializer(op, context=self.get_serializer_context()).data,
                    'questions': [
                        QuestionSerializer(q).data for q in e.questions
                    ]
                }, status=400)
            except CheckInError as e:
                op.order.log_action('pretix.event.checkin.denied', data={
                    'position': op.id,
                    'positionid': op.positionid,
                    'errorcode': e.code,
                    'reason_explanation': e.reason,
                    'force': force,
                    'datetime': dt,
                    'type': type,
                    'list': self.checkinlist.pk
                }, user=self.request.user, auth=self.request.auth)
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
                    'require_attention': op.item.checkin_attention or op.order.checkin_attention,
                    'position': CheckinListOrderPositionSerializer(op, context=self.get_serializer_context()).data
                }, status=400)
            else:
                return Response({
                    'status': 'ok',
                    'require_attention': op.item.checkin_attention or op.order.checkin_attention,
                    'position': CheckinListOrderPositionSerializer(op, context=self.get_serializer_context()).data
                }, status=201)

    def _handle_file_upload(self, data):
        try:
            cf = CachedFile.objects.get(
                session_key=f'api-upload-{str(type(self.request.user or self.request.auth))}-{(self.request.user or self.request.auth).pk}',
                file__isnull=False,
                pk=data[len("file:"):],
            )
        except (ValidationError, IndexError):  # invalid uuid
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
