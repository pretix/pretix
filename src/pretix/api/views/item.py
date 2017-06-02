from rest_framework import viewsets

from pretix.api.serializers.item import ItemSerializer
from pretix.base.models import Item


class ItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemSerializer
    queryset = Item.objects.none()

    def get_queryset(self):
        return self.request.event.items.all()
