#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, viewsets

from pretix.api.pagination import TotalOrderingFilter
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.models import ItemVariation, SalesChannel
from pretix.plugins.autocheckin.models import AutoCheckinRule
from pretix.plugins.sendmail.models import Rule


class AutoCheckinRuleSerializer(I18nAwareModelSerializer):
    limit_sales_channels = serializers.SlugRelatedField(
        slug_field="identifier",
        queryset=SalesChannel.objects.none(),
        required=False,
        allow_empty=True,
        many=True,
    )

    class Meta:
        model = AutoCheckinRule
        fields = [
            "id",
            "list",
            "mode",
            "all_sales_channels",
            "limit_sales_channels",
            "all_products",
            "limit_products",
            "limit_variations",
            "all_payment_methods",
            "limit_payment_methods",
        ]
        read_only_fields = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["limit_sales_channels"].child_relation.queryset = self.context[
            "event"
        ].organizer.sales_channels.all()
        self.fields["limit_products"].child_relation.queryset = self.context[
            "event"
        ].items.all()
        self.fields["limit_variations"].child_relation.queryset = (
            ItemVariation.objects.filter(item__event=self.context["event"])
        )
        self.fields["limit_payment_methods"] = serializers.MultipleChoiceField(
            choices=[
                (f.identifier, f.verbose_name)
                for f in self.context["event"].get_payment_providers().values()
            ],
            required=False,
            allow_empty=True,
        )

    def validate(self, data):
        data = super().validate(data)

        full_data = (
            self.to_internal_value(self.to_representation(self.instance))
            if self.instance
            else {}
        )
        full_data.update(data)

        if full_data.get("mode") == AutoCheckinRule.MODE_PLACED and not full_data.get(
            "all_payment_methods"
        ):
            raise ValidationError("all_payment_methods should be used for mode=placed")

        if isinstance(full_data.get("limit_payment_methods"), set):
            full_data["limit_payment_methods"] = list(
                full_data["limit_payment_methods"]
            )

        return full_data

    def save(self, **kwargs):
        return super().save(event=self.context["request"].event)


class RuleViewSet(viewsets.ModelViewSet):
    queryset = Rule.objects.none()
    serializer_class = AutoCheckinRuleSerializer
    filter_backends = (DjangoFilterBackend, TotalOrderingFilter)
    ordering = ("id",)
    ordering_fields = ("id",)
    permission = "can_change_event_settings"

    def get_queryset(self):
        return AutoCheckinRule.objects.filter(event=self.request.event)

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            "event": self.request.event,
        }

    def perform_create(self, serializer):
        super().perform_create(serializer)
        serializer.instance.log_action(
            "pretix.plugins.autocheckin.rule.added",
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )

    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            "pretix.plugins.autocheckin.rule.changed",
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )

    def perform_destroy(self, instance):
        instance.log_action(
            "pretix.plugins.autocheckin.rule.deleted",
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )
        super().perform_destroy(instance)
