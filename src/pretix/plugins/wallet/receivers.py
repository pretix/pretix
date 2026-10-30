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

from django.dispatch import receiver

from pretix.base.signals import (
    register_global_settings, register_ticket_outputs,
    order_canceled,
    order_changed,
    order_paid,
    periodic_task,
)
from pretix.control.signals import item_forms

from .forms import WalletLayoutItemForm
from .models import WalletLayoutItem
from .ticketoutput import WalletSettingsHolder
from .platforms import AVAILABLE_PLATFORMS

@receiver(register_ticket_outputs, dispatch_uid="output_wallet")
def register_output(sender, **kwargs):
    return WalletSettingsHolder

for platform in AVAILABLE_PLATFORMS:
    if hasattr(platform, "get_global_settings"):
        register_global_settings.connect(
            platform.get_global_settings,
            dispatch_uid=f"wallet_global_settings_{platform.identifier}",
        )


@receiver(item_forms, dispatch_uid="pretix_wallet_item_forms")
def control_item_forms(sender, request, item, **kwargs):
    forms = []
    try:
        inst = WalletLayoutItem.objects.get(item=item)
    except WalletLayoutItem.DoesNotExist:
        inst = WalletLayoutItem(item=item)
    forms.append(
        WalletLayoutItemForm(
            instance=inst,
            event=sender,
            data=(request.POST if request.method == "POST" else None),
            prefix="wallet",
        )
    )
    return forms


@receiver(periodic_task, dispatch_uid="wallet_periodic")
def periodic_tasks(sender, **kwargs):
    from .tasks import send_update_apns
    send_update_apns.apply_async()