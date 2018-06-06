from rest_framework import viewsets

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField

from .models import BadgeItem, BadgeLayout


class ItemAssignmentSerializer(I18nAwareModelSerializer):
    class Meta:
        model = BadgeItem
        fields = ('item',)


class BadgeLayoutSerializer(I18nAwareModelSerializer):
    layout = CompatibleJSONField()
    item_assignments = ItemAssignmentSerializer(many=True)

    class Meta:
        model = BadgeLayout
        fields = ('id', 'name', 'default', 'layout', 'background', 'item_assignments')


class BadgeLayoutViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BadgeLayoutSerializer
    queryset = BadgeLayout.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return self.request.event.badge_layouts.all()
