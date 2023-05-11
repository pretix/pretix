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
from decimal import Decimal

import django_filters
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from django_scopes import scopes_disabled
from rest_framework import mixins, serializers, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from pretix.api.models import OAuthAccessToken
from pretix.api.pagination import TotalOrderingFilter
from pretix.api.serializers.organizer import (
    CustomerCreateSerializer, CustomerSerializer, DeviceSerializer,
    GiftCardSerializer, GiftCardTransactionSerializer, MembershipSerializer,
    MembershipTypeSerializer, OrganizerSerializer, OrganizerSettingsSerializer,
    SeatingPlanSerializer, TeamAPITokenSerializer, TeamInviteSerializer,
    TeamMemberSerializer, TeamSerializer,
)
from pretix.base.models import (
    Customer, Device, GiftCard, GiftCardTransaction, Membership,
    MembershipType, Organizer, SeatingPlan, Team, TeamAPIToken, TeamInvite,
    User,
)
from pretix.base.settings import SETTINGS_AFFECTING_CSS
from pretix.helpers import OF_SELF
from pretix.helpers.dicts import merge_dicts
from pretix.presale.style import regenerate_organizer_css


class OrganizerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizerSerializer
    queryset = Organizer.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'organizer'
    lookup_value_regex = '[^/]+'
    filter_backends = (TotalOrderingFilter,)
    ordering = ('slug',)
    ordering_fields = ('name', 'slug')

    def get_queryset(self):
        if self.request.user.is_authenticated:
            if self.request.user.has_active_staff_session(self.request.session.session_key):
                return Organizer.objects.all()
            elif isinstance(self.request.auth, OAuthAccessToken):
                return Organizer.objects.filter(
                    pk__in=self.request.user.teams.values_list('organizer', flat=True)
                ).filter(
                    pk__in=self.request.auth.organizers.values_list('pk', flat=True)
                )
            else:
                return Organizer.objects.filter(pk__in=self.request.user.teams.values_list('organizer', flat=True))
        elif hasattr(self.request.auth, 'organizer_id'):
            return Organizer.objects.filter(pk=self.request.auth.organizer_id)
        else:
            return Organizer.objects.filter(pk=self.request.auth.team.organizer_id)


class SeatingPlanViewSet(viewsets.ModelViewSet):
    serializer_class = SeatingPlanSerializer
    queryset = SeatingPlan.objects.none()
    permission = 'can_change_organizer_settings'
    write_permission = 'can_change_organizer_settings'

    def get_queryset(self):
        return self.request.organizer.seating_plans.order_by('name')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.seatingplan.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        if serializer.instance.events.exists() or serializer.instance.subevents.exists():
            raise PermissionDenied('This plan can not be changed while it is in use for an event.')
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.seatingplan.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': serializer.instance.pk})
        )
        return inst

    @transaction.atomic()
    def perform_destroy(self, instance):
        if instance.events.exists() or instance.subevents.exists():
            raise PermissionDenied('This plan can not be deleted while it is in use for an event.')
        instance.log_action(
            'pretix.seatingplan.deleted',
            user=self.request.user,
            auth=self.request.auth,
            data={'id': instance.pk}
        )
        instance.delete()


with scopes_disabled():
    class GiftCardFilter(FilterSet):
        secret = django_filters.CharFilter(field_name='secret', lookup_expr='iexact')

        class Meta:
            model = GiftCard
            fields = ['secret', 'testmode']


class GiftCardViewSet(viewsets.ModelViewSet):
    serializer_class = GiftCardSerializer
    queryset = GiftCard.objects.none()
    permission = 'can_manage_gift_cards'
    write_permission = 'can_manage_gift_cards'
    filter_backends = (DjangoFilterBackend,)
    filterset_class = GiftCardFilter

    def get_queryset(self):
        if self.request.GET.get('include_accepted') == 'true':
            qs = self.request.organizer.accepted_gift_cards
        else:
            qs = self.request.organizer.issued_gift_cards.all()
        return qs.prefetch_related(
            'issuer'
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        value = serializer.validated_data.pop('value')
        inst = serializer.save(issuer=self.request.organizer)
        inst.transactions.create(value=value, acceptor=self.request.organizer)
        inst.log_action(
            'pretix.giftcards.transaction.manual',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        if 'include_accepted' in self.request.GET:
            raise PermissionDenied("Accepted gift cards cannot be updated, use transact instead.")
        GiftCard.objects.select_for_update(of=OF_SELF).get(pk=self.get_object().pk)

        value = serializer.validated_data.pop('value', None)

        if any(k != 'value' for k in self.request.data):
            inst = serializer.save(secret=serializer.instance.secret, currency=serializer.instance.currency,
                                   testmode=serializer.instance.testmode)
            inst.log_action(
                'pretix.giftcards.modified',
                user=self.request.user,
                auth=self.request.auth,
                data=self.request.data,
            )
        else:
            inst = serializer.instance

        if 'value' in self.request.data and value is not None:
            old_value = serializer.instance.value
            diff = value - old_value
            inst.transactions.create(value=diff, acceptor=self.request.organizer)
            inst.log_action(
                'pretix.giftcards.transaction.manual',
                user=self.request.user,
                auth=self.request.auth,
                data={'value': diff}
            )

        return inst

    @action(detail=True, methods=["POST"])
    @transaction.atomic()
    def transact(self, request, **kwargs):
        gc = GiftCard.objects.select_for_update(of=OF_SELF).get(pk=self.get_object().pk)
        value = serializers.DecimalField(max_digits=13, decimal_places=2).to_internal_value(
            request.data.get('value')
        )
        text = serializers.CharField(allow_blank=True, allow_null=True).to_internal_value(
            request.data.get('text', '')
        )
        info = serializers.JSONField(required=False, allow_null=True).to_internal_value(
            request.data.get('info', {})
        )
        if gc.value + value < Decimal('0.00'):
            return Response({
                'value': ['The gift card does not have sufficient credit for this operation.']
            }, status=status.HTTP_409_CONFLICT)
        gc.transactions.create(value=value, text=text, info=info, acceptor=self.request.organizer)
        gc.log_action(
            'pretix.giftcards.transaction.manual',
            user=self.request.user,
            auth=self.request.auth,
            data={'value': value, 'text': text}
        )
        return Response(GiftCardSerializer(gc, context=self.get_serializer_context()).data, status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        raise MethodNotAllowed("Gift cards cannot be deleted.")


class GiftCardTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = GiftCardTransactionSerializer
    queryset = GiftCardTransaction.objects.none()
    permission = 'can_manage_gift_cards'
    write_permission = 'can_manage_gift_cards'

    @cached_property
    def giftcard(self):
        if self.request.GET.get('include_accepted') == 'true':
            qs = self.request.organizer.accepted_gift_cards
        else:
            qs = self.request.organizer.issued_gift_cards.all()
        return get_object_or_404(qs, pk=self.kwargs.get('giftcard'))

    def get_queryset(self):
        return self.giftcard.transactions.select_related('order', 'order__event').prefetch_related('acceptor')


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    queryset = Team.objects.none()
    permission = 'can_change_teams'
    write_permission = 'can_change_teams'

    def get_queryset(self):
        return self.request.organizer.teams.order_by('pk')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        inst.log_action(
            'pretix.team.created',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        inst = serializer.save()
        inst.log_action(
            'pretix.team.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )
        return inst

    def perform_destroy(self, instance):
        instance.log_action('pretix.team.deleted', user=self.request.user, auth=self.request.auth)
        instance.delete()


class TeamMemberViewSet(DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TeamMemberSerializer
    queryset = User.objects.none()
    permission = 'can_change_teams'
    write_permission = 'can_change_teams'

    @cached_property
    def team(self):
        return get_object_or_404(self.request.organizer.teams, pk=self.kwargs.get('team'))

    def get_queryset(self):
        return self.team.members.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    @transaction.atomic()
    def perform_destroy(self, instance):
        self.team.members.remove(instance)
        self.team.log_action(
            'pretix.team.member.removed', user=self.request.user, auth=self.request.auth, data={
                'email': instance.email,
                'user': instance.pk
            }
        )


class TeamInviteViewSet(CreateModelMixin, DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TeamInviteSerializer
    queryset = TeamInvite.objects.none()
    permission = 'can_change_teams'
    write_permission = 'can_change_teams'

    @cached_property
    def team(self):
        return get_object_or_404(self.request.organizer.teams, pk=self.kwargs.get('team'))

    def get_queryset(self):
        return self.team.invites.order_by('email')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        ctx['team'] = self.team
        ctx['log_kwargs'] = {
            'user': self.request.user,
            'auth': self.request.auth,
        }
        return ctx

    @transaction.atomic()
    def perform_destroy(self, instance):
        self.team.log_action(
            'pretix.team.invite.deleted', user=self.request.user, auth=self.request.auth, data={
                'email': instance.email,
            }
        )
        instance.delete()

    @transaction.atomic()
    def perform_create(self, serializer):
        serializer.save(team=self.team)


class TeamAPITokenViewSet(CreateModelMixin, DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = TeamAPITokenSerializer
    queryset = TeamAPIToken.objects.none()
    permission = 'can_change_teams'
    write_permission = 'can_change_teams'

    @cached_property
    def team(self):
        return get_object_or_404(self.request.organizer.teams, pk=self.kwargs.get('team'))

    def get_queryset(self):
        return self.team.tokens.order_by('name')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        ctx['team'] = self.team
        ctx['log_kwargs'] = {
            'user': self.request.user,
            'auth': self.request.auth,
        }
        return ctx

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.active = False
        instance.save()
        self.team.log_action(
            'pretix.team.token.deleted', user=self.request.user, auth=self.request.auth, data={
                'name': instance.name,
            }
        )

    @transaction.atomic()
    def perform_create(self, serializer):
        instance = serializer.save(team=self.team)
        self.team.log_action(
            'pretix.team.token.created', auth=self.request.auth, user=self.request.user, data={
                'name': instance.name,
                'id': instance.pk
            }
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        d = serializer.data
        d['token'] = serializer.instance.token
        return Response(d, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        serializer = self.get_serializer_class()(instance)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_200_OK, headers=headers)


class DeviceViewSet(mixins.CreateModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.UpdateModelMixin,
                    mixins.ListModelMixin,
                    GenericViewSet):
    serializer_class = DeviceSerializer
    queryset = Device.objects.none()
    permission = 'can_change_organizer_settings'
    write_permission = 'can_change_organizer_settings'
    lookup_field = 'device_id'

    def get_queryset(self):
        return self.request.organizer.devices.order_by('pk')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        inst.log_action(
            'pretix.device.created',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        inst = serializer.save()
        inst.log_action(
            'pretix.device.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data
        )
        return inst


class OrganizerSettingsView(views.APIView):
    permission = 'can_change_organizer_settings'

    def get(self, request, *args, **kwargs):
        s = OrganizerSettingsSerializer(instance=request.organizer.settings, organizer=request.organizer, context={
            'request': request
        })
        if 'explain' in request.GET:
            return Response({
                fname: {
                    'value': s.data[fname],
                    'label': getattr(field, '_label', fname),
                    'help_text': getattr(field, '_help_text', None),
                    'readonly': fname in s.readonly_fields,
                } for fname, field in s.fields.items()
            })
        return Response(s.data)

    def patch(self, request, *wargs, **kwargs):
        s = OrganizerSettingsSerializer(
            instance=request.organizer.settings, data=request.data, partial=True,
            organizer=request.organizer, context={
                'request': request
            }
        )
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            s.save()
            self.request.organizer.log_action(
                'pretix.organizer.settings', user=self.request.user, auth=self.request.auth, data={
                    k: v for k, v in s.validated_data.items()
                }
            )
        if any(p in s.changed_data for p in SETTINGS_AFFECTING_CSS):
            regenerate_organizer_css.apply_async(args=(request.organizer.pk,))
        s = OrganizerSettingsSerializer(instance=request.organizer.settings, organizer=request.organizer, context={
            'request': request
        })
        return Response(s.data)


with scopes_disabled():
    class CustomerFilter(FilterSet):
        email = django_filters.CharFilter(field_name='email', lookup_expr='iexact')

        class Meta:
            model = Customer
            fields = ['email']


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    queryset = Customer.objects.none()
    permission = 'can_manage_customers'
    lookup_field = 'identifier'
    filter_backends = (DjangoFilterBackend,)
    filterset_class = CustomerFilter

    def get_queryset(self):
        qs = self.request.organizer.customers.all()
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    def perform_destroy(self, instance):
        raise MethodNotAllowed("Customers cannot be deleted.")

    @transaction.atomic()
    def perform_create(self, serializer, send_email=False, password=None):
        customer = serializer.save(organizer=self.request.organizer, password=make_password(password))
        serializer.instance.log_action(
            'pretix.customer.created',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        if send_email:
            customer.send_activation_mail()
        return customer

    def create(self, request, *args, **kwargs):
        serializer = CustomerCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer, send_email=serializer.validated_data.pop('send_email', False), password=serializer.validated_data.pop('password', None))
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @transaction.atomic()
    def perform_update(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        serializer.instance.log_action(
            'pretix.customer.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        return inst

    @action(detail=True, methods=["POST"])
    @transaction.atomic()
    def anonymize(self, request, **kwargs):
        o = self.get_object()
        o.anonymize()
        o.log_action('pretix.customer.anonymized', user=self.request.user, auth=self.request.auth)
        return Response(CustomerSerializer(o).data, status=status.HTTP_200_OK)


class MembershipTypeViewSet(viewsets.ModelViewSet):
    serializer_class = MembershipTypeSerializer
    queryset = MembershipType.objects.none()
    permission = 'can_change_organizer_settings'

    def get_queryset(self):
        qs = self.request.organizer.membership_types.all()
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    def perform_destroy(self, instance):
        if not instance.allow_delete():
            raise PermissionDenied("Can only be deleted if unused.")
        instance.log_action(
            'pretix.membershiptype.deleted',
            user=self.request.user,
            auth=self.request.auth,
            data={'id': instance.pk}
        )
        instance.delete()

    @transaction.atomic()
    def perform_create(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        serializer.instance.log_action(
            'pretix.membershiptype.created',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        return inst

    @transaction.atomic()
    def perform_update(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        serializer.instance.log_action(
            'pretix.membershiptype.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        return inst


with scopes_disabled():
    class MembershipFilter(FilterSet):
        customer = django_filters.CharFilter(field_name='customer__identifier', lookup_expr='iexact')

        class Meta:
            model = Membership
            fields = ['customer', 'membership_type', 'testmode']


class MembershipViewSet(viewsets.ModelViewSet):
    serializer_class = MembershipSerializer
    queryset = Membership.objects.none()
    permission = 'can_manage_customers'
    filter_backends = (DjangoFilterBackend,)
    filterset_class = MembershipFilter

    def get_queryset(self):
        return Membership.objects.filter(
            customer__organizer=self.request.organizer
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    def perform_destroy(self, instance):
        raise MethodNotAllowed("Memberships cannot be deleted. You can change the date instead.")

    @transaction.atomic()
    def perform_create(self, serializer):
        inst = serializer.save()
        serializer.instance.customer.log_action(
            'pretix.customer.membership.created',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        return inst

    @transaction.atomic()
    def perform_update(self, serializer):
        inst = serializer.save()
        serializer.instance.customer.log_action(
            'pretix.customer.membership.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        return inst
