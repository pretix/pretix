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

from collections import OrderedDict

from django import forms
from django.db.models import Exists, OuterRef
from django.dispatch import receiver
from django.template.loader import get_template
from django.utils.translation import gettext as _

from pretix.base.forms import SecretKeySettingsField
from pretix.base.models.event import Event
from pretix.base.shredder import BaseDataShredder, slow_delete
from pretix.base.signals import (
    invalidate_ticket_cache, periodic_task, register_data_shredders,
    register_global_settings,
)
from pretix.base.wallet.tasks import get_pass
from pretix.control.forms import ClearableBasenameFileInput
from pretix.control.signals import html_head

from .forms import CertificateFileField, validate_rsa_privkey
from .models import AppleWalletDevice, AppleWalletPass, CombinedAppleWalletPass
from .tasks import send_update_apns


@receiver(periodic_task, dispatch_uid="wallet_periodic")
def periodic_tasks(sender, **kwargs):
    send_update_apns.apply_async()


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
    template = get_template("pretixplugins/apple_wallet/control_head.html")
    return template.render({})


class AppleWalletShredder(BaseDataShredder):
    verbose_name = _("Apple Wallet")
    identifier = "apple_wallet"
    description = _(
        "This will remove all data regarding apple wallet passes. Passes can no longer be automatically updated "
        "after this data is deleted. No download will be offered."
    )

    def generate_files(self):
        pass

    def shred_data(self, progress_callback=None):
        qs_1 = AppleWalletDevice.objects.filter(
            Exists(
                AppleWalletPass.objects.filter(
                    registered_devices=OuterRef("pk"),
                    order_position__order__event=self.event,
                )
            ),
            ~Exists(
                AppleWalletPass.objects.filter(
                    registered_devices=OuterRef("pk")
                ).exclude(order_position__order__event=self.event)
            ),
        )
        qs_1_count = qs_1.count()

        qs_2 = AppleWalletPass.objects.filter(order_position__order__event=self.event)
        qs_2_count = qs_2.count()

        qs_3 = CombinedAppleWalletPass.objects.filter(order__event=self.event)
        qs_3_count = qs_3.count()

        total = qs_1_count + qs_2_count + qs_3_count

        slow_delete(qs_1, progress_callback=progress_callback, progress_total=total)
        slow_delete(
            qs_2,
            progress_callback=progress_callback,
            progress_total=total,
            progress_offset=qs_1_count,
        )
        slow_delete(
            qs_3,
            progress_callback=progress_callback,
            progress_total=total,
            progress_offset=qs_1_count + qs_2_count,
        )


@receiver(register_data_shredders, dispatch_uid="shredders_apple_wallet")
def shredders_apple_wallet(**kwargs):
    return [AppleWalletShredder]


@receiver(register_global_settings, dispatch_uid="apple_wallet_global_settings")
def global_settings_apple_wallet(**kwargs):
    return OrderedDict(
        [
            (
                # TODO: extract from pass certificate
                "wallet_apple_team_id",
                forms.CharField(
                    label=_("Apple Wallet Pass team ID"),
                    required=False,
                ),
            ),
            (
                # TODO: extract from pass certificate
                "wallet_apple_pass_type_id",
                forms.CharField(
                    label=_("Apple Wallet Pass type"),
                    required=False,
                ),
            ),
            (
                "wallet_apple_certificate",
                CertificateFileField(
                    label=_("Apple Wallet Pass certificate file"),
                    required=False,
                ),
            ),
            (
                # TODO: download this server-side
                "wallet_apple_ca_certificate",
                CertificateFileField(
                    label=_("Apple Wallet Pass CA Certificate"),
                    help_text=_(
                        "You can download the current CA certificate from apple at "
                        "https://www.apple.com/certificateauthority/AppleWWDRCAG4.cer"
                    ),
                    required=False,
                ),
            ),
            (
                "wallet_apple_key",
                forms.FileField(
                    label=_("Apple Wallet Pass secret key"),
                    required=False,
                    validators=[validate_rsa_privkey],
                    widget=ClearableBasenameFileInput,
                ),
            ),
            (
                "wallet_apple_key_password",
                SecretKeySettingsField(
                    label=_("Apple Wallet Pass key password"),
                    required=False,
                    help_text=_(
                        "Optional, only necessary if the key entered above requires a password to use."
                    ),
                ),
            ),
        ]
    )
