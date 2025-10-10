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
from datetime import timedelta

from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.api.models import ApiCall, WebHookCall
from pretix.base.signals import EventPluginSignal, GlobalSignal, periodic_task
from pretix.helpers.periodic import minimum_interval

register_webhook_events = GlobalSignal()
"""
This signal is sent out to get all known webhook events. Receivers should return an
instance of a subclass of ``pretix.api.webhooks.WebhookEvent`` or a list of such
instances.
"""

register_device_security_profile = GlobalSignal()
"""
This signal is sent out to get all known device security_profiles. Receivers should
return an instance of a subclass of ``pretix.api.auth.devicesecurity.BaseSecurityProfile``
or a list of such instances.
"""

order_api_details = EventPluginSignal()
"""
Arguments: ``order``

This signal is sent out to fill the ``plugin_details`` field of the order API. Receivers
should return a dictionary that is combined with the dictionaries of all other plugins.
Note that doing database or network queries in receivers to this signal is discouraged
and could cause serious performance issues. The main purpose is to provide information
from e.g. ``meta_info`` to the API consumer,
"""

orderposition_api_details = EventPluginSignal()
"""
Arguments: ``orderposition``

This signal is sent out to fill the ``plugin_details`` field of the order API. Receivers
should return a dictionary that is combined with the dictionaries of all other plugins.
Note that doing database or network queries in receivers to this signal is discouraged
and could cause serious performance issues. The main purpose is to provide information
from e.g. ``meta_info`` to the API consumer,
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
