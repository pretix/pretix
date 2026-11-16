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

from pretix.base.models.event import Event
from pretix.base.signals import (
    invalidate_ticket_cache,
    periodic_task,
)

from .tasks import send_update_apns
from .models import AppleWalletPass, CombinedAppleWalletPass
from pretix.base.wallet.tasks import get_pass
from pretix.control.signals import html_head
from django.template.loader import get_template


@receiver(periodic_task, dispatch_uid="wallet_periodic")
def periodic_tasks(sender, **kwargs):
    # TODO: move to platform?
    send_update_apns.apply_async()


# TODO: move to platform?
@receiver(invalidate_ticket_cache, dispatch_uid="invalidate_ticket_cache_wallet_apple")
def invalidate_apple(
    sender: Event, item: int | None, provider: str | None, order: int | None, **kwargs
):
    if provider and provider != "wallet":
        return

    pass_qs = AppleWalletPass.objects.filter(order_position__order__event=sender)
    passes_qs = CombinedAppleWalletPass.objects.filter(order__event=sender)

    if item:
        pass_qs = pass_qs.filter(order_position__item_id=item)
        passes_qs = passes_qs.filter(order__all_positions__item_id=item)

    if order:
        pass_qs = pass_qs.filter(order_position__order_id=order)
        passes_qs = passes_qs.filter(order_id=order)

    for pass_obj in pass_qs:
        get_pass.apply_async(
            kwargs={
                "model": "orderposition",
                "pk": pass_obj.order_position_id,
                "platform_identifier": "apple",
                "show_disabled": False,
            }
        )

    for passes_obj in passes_qs:
        passes_obj.delete()


@receiver(html_head, dispatch_uid="html_head_apple_wallet")
def html_head_apple_wallet(request, **kwargs):
    template = get_template('pretixplugins/apple_wallet/control_head.html')
    return template.render({})
