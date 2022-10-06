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
from rest_framework import viewsets

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField

from ...multidomain.utils import static_absolute
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

    def to_representation(self, instance):
        d = super().to_representation(instance)
        if not d['background']:
            d['background'] = static_absolute(instance.event, "pretixpresale/pdf/ticket_default_a4.pdf")
        return d


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
