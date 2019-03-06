from rest_framework import viewsets

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField

from .models import TicketLayout, TicketLayoutItem


class ItemAssignmentSerializer(I18nAwareModelSerializer):

    class Meta:
        model = TicketLayoutItem
        fields = ('id', 'layout', 'item', 'sales_channel')


class NestedItemAssignmentSerializer(I18nAwareModelSerializer):

    class Meta:
        model = TicketLayoutItem
        fields = ('item', 'sales_channel')


class TicketLayoutSerializer(I18nAwareModelSerializer):
    layout = CompatibleJSONField()
    item_assignments = NestedItemAssignmentSerializer(many=True)

    class Meta:
        model = TicketLayout
        fields = ('id', 'name', 'default', 'layout', 'background', 'item_assignments')


class TicketLayoutViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TicketLayoutSerializer
    queryset = TicketLayout.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return self.request.event.ticket_layouts.all()


class TicketLayoutItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemAssignmentSerializer
    queryset = TicketLayoutItem.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return TicketLayoutItem.objects.filter(item__event=self.request.event)
