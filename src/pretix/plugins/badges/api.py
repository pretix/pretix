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

    def to_representation(self, instance):
        d = super().to_representation(instance)
        if not d['background']:
            d['background'] = static_absolute(instance.event, "pretixplugins/badges/badge_default_a6l.pdf")
        return d


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
