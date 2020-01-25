from decimal import Decimal

from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField
from pretix.base.models import (
    GiftCard, Organizer, SeatingPlan, Team, TeamAPIToken, TeamInvite, User,
)
from pretix.base.models.seating import SeatingPlanLayoutValidator


class OrganizerSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Organizer
        fields = ('name', 'slug')


class SeatingPlanSerializer(I18nAwareModelSerializer):
    layout = CompatibleJSONField(
        validators=[SeatingPlanLayoutValidator()]
    )

    class Meta:
        model = SeatingPlan
        fields = ('id', 'name', 'layout')


class GiftCardSerializer(I18nAwareModelSerializer):
    value = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.00'))

    def validate(self, data):
        data = super().validate(data)
        s = data['secret']
        qs = GiftCard.objects.filter(
            secret=s
        ).filter(
            Q(issuer=self.context["organizer"]) | Q(
                issuer__gift_card_collector_acceptance__collector=self.context["organizer"])
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                {'secret': _(
                    'A gift card with the same secret already exists in your or an affiliated organizer account.')}
            )
        return data

    class Meta:
        model = GiftCard
        fields = ('id', 'secret', 'issuance', 'value', 'currency', 'testmode')


class EventSlugField(serializers.SlugRelatedField):
    def get_queryset(self):
        return self.context['organizer'].events.all()


class TeamSerializer(serializers.ModelSerializer):
    limit_events = EventSlugField(slug_field='slug', many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Team
        fields = (
            'id', 'name', 'all_events', 'limit_events', 'can_create_events', 'can_change_teams',
            'can_change_organizer_settings', 'can_manage_gift_cards', 'can_change_event_settings',
            'can_change_items', 'can_view_orders', 'can_change_orders', 'can_view_vouchers',
            'can_change_vouchers'
        )

    def validate(self, data):
        full_data = self.to_internal_value(self.to_representation(self.instance)) if self.instance else {}
        full_data.update(data)
        if full_data.get('limit_events') and full_data.get('all_events'):
            raise ValidationError('Do not set both limit_events and all_events.')
        return data


class TeamInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamInvite
        fields = (
            'id', 'email'
        )


class TeamAPITokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamAPIToken
        fields = (
            'id', 'name', 'active'
        )


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id', 'email', 'fullname', 'require_2fa'
        )
