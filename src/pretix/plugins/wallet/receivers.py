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
    register_global_settings,
    register_ticket_outputs,
    invalidate_ticket_cache,
    periodic_task,
)
from pretix.control.signals import item_forms
from pretix.plugins.wallet.platforms.google.platform import get_object_id

from .forms import WalletLayoutItemForm
from .models import WalletLayout, WalletLayoutItem
from .ticketoutput import WalletSettingsHolder
from .platforms import wallet_platform_registry
from .tasks import disable_wallet_instance, send_update_apns
from .models import AppleWalletPass, CombinedAppleWalletPass
from .tasks import get_pass
from .models import GoogleWalletInstance

from django.utils.translation import gettext as _
from pretix.base.logentrytypes import log_entry_types, EventLogEntryType


@receiver(register_ticket_outputs, dispatch_uid="output_wallet")
def register_output(sender, **kwargs):
    return WalletSettingsHolder


for platform in wallet_platform_registry.all():
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


@receiver(invalidate_ticket_cache, dispatch_uid="invalidate_ticket_cache_wallet_google")
def invalidate_google(
    sender: Event, item: int | None, provider: str | None, order: int | None, **kwargs
):
    if provider and provider != "wallet":
        return

    inst_qs = GoogleWalletInstance.objects.filter(event=sender).exclude(
        order_position__isnull=True
    )

    if item:
        inst_qs = inst_qs.filter(order_position__item_id=item)

    if order:
        inst_qs = inst_qs.filter(order_position__order_id=order)

    for inst in inst_qs:
        if get_object_id(inst.order_position) != inst.identifier:
            # the OPs web_secret was changed
            disable_wallet_instance.apply_async(kwargs={"pk": inst.pk})
        get_pass.apply_async(
            kwargs={
                "model": "orderposition",
                "pk": inst.order_position_id,
                "platform_identifier": "google",
                "show_disabled": False,
            }
        )


@log_entry_types.new_from_dict(
    {
        "pretix.plugins.wallet.layout.created": _(
            "The wallet layout has been created."
        ),
        "pretix.plugins.wallet.layout.changed": _(
            "The wallet layout has been changed."
        ),
        "pretix.plugins.wallet.layout.deleted": _(
            "The wallet layout has been deleted."
        ),
    }
)
class WalletLogEntryType(EventLogEntryType):
    object_link_wrapper = _("Wallet Layout {val}")
    object_link_viewname = "plugins:wallet:edit"
    content_type = WalletLayout

    def object_link_args(self, content_object):
        return {"layout": content_object.pk}

    def object_link_display_name(self, content_object):
        return content_object.name
