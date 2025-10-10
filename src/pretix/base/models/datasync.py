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

import logging
from functools import cached_property

from django.db import IntegrityError, models
from django.utils.translation import gettext as _

from pretix.base.models import Event, Order, OrderPosition

logger = logging.getLogger(__name__)


MODE_OVERWRITE = "overwrite"
MODE_SET_IF_NEW = "if_new"
MODE_SET_IF_EMPTY = "if_empty"
MODE_APPEND_LIST = "append"


class OrderSyncQueue(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="queued_sync_jobs"
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="queued_sync_jobs"
    )
    sync_provider = models.CharField(blank=False, null=False, max_length=128)
    triggered_by = models.CharField(blank=False, null=False, max_length=128)
    triggered = models.DateTimeField(blank=False, null=False, auto_now_add=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    not_before = models.DateTimeField(blank=False, null=False, db_index=True)
    need_manual_retry = models.CharField(blank=True, null=True, max_length=20, choices=[
        ('exceeded', _('Temporary error, auto-retry limit exceeded')),
        ('permanent', _('Provider reported a permanent error')),
        ('config', _('Misconfiguration, please check provider settings')),
        ('internal', _('System error, needs manual intervention')),
        ('timeout', _('System error, needs manual intervention')),
    ])
    in_flight = models.BooleanField(default=False)
    in_flight_since = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = (("order", "sync_provider", "in_flight"),)
        ordering = ("triggered",)

    @cached_property
    def _provider_class_info(self):
        from pretix.base.datasync.datasync import datasync_providers
        return datasync_providers.get(identifier=self.sync_provider)

    @property
    def provider_class(self):
        return self._provider_class_info[0]

    @property
    def provider_display_name(self):
        return self.provider_class.display_name

    @property
    def is_provider_active(self):
        return self._provider_class_info[1]

    @property
    def max_retry_attempts(self):
        return self.provider_class.max_attempts

    def set_sync_error(self, failure_mode, messages, full_message):
        logger.exception(
            f"Could not sync order {self.order.code} to {type(self).__name__} ({failure_mode})"
        )
        self.order.log_action(f"pretix.event.order.data_sync.failed.{failure_mode}", {
            "provider": self.sync_provider,
            "error": messages,
            "full_message": full_message,
        })
        self.need_manual_retry = failure_mode
        self.clear_in_flight()

    def clear_in_flight(self):
        self.in_flight = False
        self.in_flight_since = None
        try:
            self.save()
        except IntegrityError:
            # if setting in_flight=False fails due to UNIQUE constraint, just delete the current instance
            self.delete()


class OrderSyncResult(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="sync_results"
    )
    sync_provider = models.CharField(blank=False, null=False, max_length=128)
    order_position = models.ForeignKey(
        OrderPosition, on_delete=models.CASCADE, related_name="sync_results", blank=True, null=True,
    )
    mapping_id = models.IntegerField(blank=False, null=False)
    external_object_type = models.CharField(blank=False, null=False, max_length=128)
    external_id_field = models.CharField(blank=False, null=False, max_length=128)
    id_value = models.CharField(blank=False, null=False, max_length=128)
    external_link_href = models.CharField(blank=True, null=True, max_length=255)
    external_link_display_name = models.CharField(blank=True, null=True, max_length=255)
    transmitted = models.DateTimeField(blank=False, null=False, auto_now_add=True)
    sync_info = models.JSONField()

    class Meta:
        indexes = [
            models.Index(fields=("order", "sync_provider")),
        ]

    def external_link_html(self):
        if not self.external_link_display_name:
            return None

        from pretix.base.datasync.datasync import datasync_providers
        prov, meta = datasync_providers.get(identifier=self.sync_provider)
        if prov:
            return prov.get_external_link_html(self.order.event, self.external_link_href, self.external_link_display_name)

    def to_result_dict(self):
        return {
            "position": self.order_position_id,
            "object_type": self.external_object_type,
            "external_id_field": self.external_id_field,
            "id_value": self.id_value,
            "external_link_href": self.external_link_href,
            "external_link_display_name": self.external_link_display_name,
            **self.sync_info,
        }
