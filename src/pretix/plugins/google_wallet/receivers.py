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
from django.template.loader import get_template

from pretix.base.models.event import Event
from pretix.base.signals import invalidate_ticket_cache
from pretix.base.wallet.tasks import get_pass
from pretix.control.signals import html_head

from .models import GoogleWalletInstance
from .platform import get_object_id
from .tasks import disable_wallet_instance


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


@receiver(html_head, dispatch_uid="html_head_google_wallet")
def html_head_google_wallet(request, **kwargs):
    template = get_template('pretixplugins/google_wallet/control_head.html')
    return template.render({})
