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

from pretix.api.models import WebHook
from pretix.api.serializers.webhooks import WebHookSerializer
from pretix.helpers.dicts import merge_dicts


class WebHookViewSet(viewsets.ModelViewSet):
    serializer_class = WebHookSerializer
    queryset = WebHook.objects.none()
    permission = 'can_change_organizer_settings'
    write_permission = 'can_change_organizer_settings'

    def get_queryset(self):
        return self.request.organizer.webhooks.prefetch_related('listeners')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['organizer'] = self.request.organizer
        return ctx

    def perform_create(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.webhook.created',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': inst.pk})
        )

    def perform_update(self, serializer):
        inst = serializer.save(organizer=self.request.organizer)
        self.request.organizer.log_action(
            'pretix.webhook.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=merge_dicts(self.request.data, {'id': serializer.instance.pk})
        )
        return inst

    def perform_destroy(self, instance):
        self.request.organizer.log_action(
            'pretix.webhook.changed',
            user=self.request.user,
            auth=self.request.auth,
            data={'id': instance.pk, 'enabled': False}
        )
        instance.enabled = False
        instance.save(update_fields=['enabled'])
