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
from datetime import timedelta

from django.dispatch import Signal, receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.api.models import ApiCall, WebHookCall
from pretix.base.signals import periodic_task
from pretix.helpers.periodic import minimum_interval

register_webhook_events = Signal()
"""
This signal is sent out to get all known webhook events. Receivers should return an
instance of a subclass of pretix.api.webhooks.WebhookEvent or a list of such
instances.
"""


@receiver(periodic_task)
@scopes_disabled()
@minimum_interval(minutes_after_success=12 * 60)
def cleanup_webhook_logs(sender, **kwargs):
    WebHookCall.objects.filter(datetime__lte=now() - timedelta(days=30)).delete()


@receiver(periodic_task)
@scopes_disabled()
@minimum_interval(minutes_after_success=12 * 60)
def cleanup_api_logs(sender, **kwargs):
    ApiCall.objects.filter(created__lte=now() - timedelta(hours=24)).delete()
