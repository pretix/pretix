from django.db.models import Q
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField
from pretix.base.models import GiftCard, Organizer, SeatingPlan
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
    value = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate(self, data):
        data = super().validate(data)
        s = data['secret']
        qs = GiftCard.objects.filter(
            secret=s
        ).filter(
            Q(issuer=self.context["organizer"]) | Q(issuer__gift_card_collector_acceptance__collector=self.context["organizer"])
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                {'secret': _('A gift card with the same secret already exists in your or an affiliated organizer account.')}
            )
        return data

    class Meta:
        model = GiftCard
        fields = ('id', 'secret', 'issuance', 'value', 'currency')
