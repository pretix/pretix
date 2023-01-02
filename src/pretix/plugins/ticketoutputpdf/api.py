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
from django.conf import settings
from django.db import transaction
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField

from ...api.serializers.fields import UploadedFileField
from ...base.pdf import PdfLayoutValidator
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
    layout = CompatibleJSONField(
        validators=[PdfLayoutValidator()]
    )
    item_assignments = NestedItemAssignmentSerializer(many=True, read_only=True)
    background = UploadedFileField(required=False, allow_null=True, allowed_types=(
        'application/pdf',
    ), max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE)

    class Meta:
        model = TicketLayout
        fields = ('id', 'name', 'default', 'layout', 'background', 'item_assignments')

    def to_representation(self, instance):
        d = super().to_representation(instance)
        if not d['background']:
            d['background'] = static_absolute(instance.event, "pretixpresale/pdf/ticket_default_a4.pdf")
        return d

    def validate(self, attrs):
        if attrs.get('default') and self.context['event'].ticket_layouts.filter(default=True).exists:
            raise ValidationError('You cannot have two layouts with default = True')
        return attrs

    def create(self, validated_data):
        validated_data["event"] = self.context["event"]
        return super().create(validated_data)


class TicketLayoutViewSet(viewsets.ModelViewSet):
    serializer_class = TicketLayoutSerializer
    queryset = TicketLayout.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return self.request.event.ticket_layouts.all()

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            'event': self.request.event,
        }

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.log_action(
            action='pretix.plugins.ticketoutputpdf.layout.deleted',
            user=self.request.user, auth=self.request.auth
        )
        super().perform_destroy(instance)
        if not self.request.event.ticket_layouts.filter(default=True).exists():
            f = self.request.event.ticket_layouts.first()
            if f:
                f.default = True
                f.save(update_fields=['default'])

    @transaction.atomic()
    def perform_create(self, serializer):
        super().perform_create(serializer)
        serializer.instance.log_action(
            action='pretix.plugins.ticketoutputpdf.layout.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            action='pretix.plugins.ticketoutputpdf.layout.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )


class TicketLayoutItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemAssignmentSerializer
    queryset = TicketLayoutItem.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return TicketLayoutItem.objects.filter(item__event=self.request.event)
