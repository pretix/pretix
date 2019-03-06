from rest_framework import viewsets

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField

from .models import BadgeItem, BadgeLayout


class BadgeItemAssignmentSerializer(I18nAwareModelSerializer):
    class Meta:
        model = BadgeItem
        fields = ('id', 'item', 'layout')


class NestedItemAssignmentSerializer(I18nAwareModelSerializer):
    class Meta:
        model = BadgeItem
        fields = ('item',)


class BadgeLayoutSerializer(I18nAwareModelSerializer):
    layout = CompatibleJSONField()
    item_assignments = NestedItemAssignmentSerializer(many=True)

    class Meta:
        model = BadgeLayout
        fields = ('id', 'name', 'default', 'layout', 'background', 'item_assignments')


class BadgeLayoutViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BadgeLayoutSerializer
    queryset = BadgeLayout.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return self.request.event.badge_layouts.all()


class BadgeItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BadgeItemAssignmentSerializer
    queryset = BadgeItem.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return BadgeItem.objects.filter(item__event=self.request.event)
