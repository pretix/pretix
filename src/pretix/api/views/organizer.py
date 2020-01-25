from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.mixins import DestroyModelMixin
from rest_framework.response import Response

from pretix.api.models import OAuthAccessToken
from pretix.api.serializers.organizer import (
    GiftCardSerializer, OrganizerSerializer, SeatingPlanSerializer,
    TeamMemberSerializer, TeamSerializer,
)
from pretix.base.models import GiftCard, Organizer, SeatingPlan, Team, User
from pretix.helpers.dicts import merge_dicts


class OrganizerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizerSerializer
    queryset = Organizer.objects.none()
    lookup_field = 'slug'
    lookup_url_kwarg = 'organizer'
    filter_backends = (filters.OrderingFilter,)
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
        return self.request.organizer.seating_plans.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    def perform_create(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.seatingplan.added',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

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


class GiftCardViewSet(viewsets.ModelViewSet):
    serializer_class = GiftCardSerializer
    queryset = GiftCard.objects.none()
    permission = 'can_manage_gift_cards'
    write_permission = 'can_manage_gift_cards'

    def get_queryset(self):
        return self.request.organizer.issued_gift_cards.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    @transaction.atomic()
    def perform_create(self, serializer):
        value = serializer.validated_data.pop('value')
        inst = serializer.save(issuer=self.request.organizer)
        inst.transactions.create(value=value)
        inst.log_action(
            'pretix.giftcards.transaction.manual',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        GiftCard.objects.select_for_update().get(pk=self.get_object().pk)
        old_value = serializer.instance.value
        value = serializer.validated_data.pop('value')
        inst = serializer.save(secret=serializer.instance.secret, currency=serializer.instance.currency,
                               testmode=serializer.instance.testmode)
        diff = value - old_value
        inst.transactions.create(value=diff)
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
        gc = GiftCard.objects.select_for_update().get(pk=self.get_object().pk)
        value = serializers.DecimalField(max_digits=10, decimal_places=2).to_internal_value(
            request.data.get('value')
        )
        if gc.value + value < Decimal('0.00'):
            return Response({
                'value': ['The gift card does not have sufficient credit for this operation.']
            }, status=status.HTTP_409_CONFLICT)
        gc.transactions.create(value=value)
        gc.log_action(
            'pretix.giftcards.transaction.manual',
            user=self.request.user,
            auth=self.request.auth,
            data={'value': value}
        )
        return Response(GiftCardSerializer(gc).data, status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        raise MethodNotAllowed("Gift cards cannot be deleted.")


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    queryset = Team.objects.none()
    permission = 'can_change_teams'
    write_permission = 'can_change_teams'

    def get_queryset(self):
        return self.request.organizer.teams.all()

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

    def perform_destroy(self, instance):
        self.team.members.remove(instance)
        self.team.log_action(
            'pretix.team.member.removed', user=self.request.user, auth=self.request.auth, data={
                'email': instance.email,
                'user': instance.pk
            }
        )
