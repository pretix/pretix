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
from django.db import models
from django.db.models import Q, constraints
from django.utils.crypto import salted_hmac, get_random_string, constant_time_compare
from django.utils.translation import gettext_lazy as _
from django_scopes import ScopedManager

from pretix.base.models import LoggedModel, OrderPosition
from pretix.base.models.orders import Order


class WalletLayout(LoggedModel):
    event = models.ForeignKey(
        "pretixbase.Event", on_delete=models.CASCADE, related_name="wallet_layouts"
    )
    name = models.CharField(max_length=190, verbose_name=_("Name"))
    default = models.BooleanField(
        verbose_name=_("Default"),
        default=False,
    )

    objects = ScopedManager(organizer="event__organizer")

    class Meta:
        constraints = [
            constraints.UniqueConstraint(
                "event", condition=Q(default=True), name="one_default_wallet_per_event"
            )
        ]
        ordering = (
            "-default",
            "name",
        )

    def __str__(self):
        return self.name

    def allow_delete(self):
        return not self.default


class WalletPlatformLayout(LoggedModel):
    parent = models.ForeignKey(
        WalletLayout, on_delete=models.CASCADE, related_name="platform_layouts"
    )

    platform = models.CharField(max_length=10)
    style = models.CharField(max_length=255)
    layout = models.JSONField(default=dict)

    objects = ScopedManager(organizer="parent__event__organizer")

    class Meta:
        unique_together = (("parent", "platform"),)

    @property
    def pass_layout(self):
        from .platforms import pass_style_registry

        style, _meta = pass_style_registry.get(active_in=self.parent.event, identifier=(self.platform, self.style))
        if style:
            file_settings = {fs.key: fs.file for fs in self.file_settings.all()}
            return style(
                event=self.parent.event, layout=self.layout, file_settings=file_settings
            )
        else:
            raise ValueError(f"Style {self.platform}.{self.style} not found")


class WalletLayoutItem(models.Model):
    item = models.OneToOneField(
        "pretixbase.Item",
        null=True,
        blank=True,
        related_name="walletlayout",
        on_delete=models.CASCADE,
    )
    layout = models.ForeignKey(
        WalletLayout,
        null=True,
        on_delete=models.CASCADE,
        related_name="item_assignments",
    )

    def clean(self):
        if self.layout and self.item.event != self.layout.event:
            raise ValidationError("cannot bind layout to item of different event")


class WalletLayoutFileSetting(models.Model):
    layout = models.ForeignKey(
        WalletPlatformLayout, on_delete=models.CASCADE, related_name="file_settings"
    )
    key = models.CharField()
    file = models.FileField()


class AppleWalletDevice(models.Model):
    device_library_id = models.CharField(unique=True)
    push_token = models.CharField()
    last_push = models.DateTimeField(auto_now_add=True)


class AppleWalletPassQuerySet(models.QuerySet):
    def get_by_auth_token(self, received_message):
        dummy = get_random_string(16)
        pk, received_token = received_message.split(":")

        try:
            pass_obj = self.get(order_position__pk=pk)
        except AppleWalletPass.DoesNotExist:
            # Do a hash comparison as well to harden against timing attacks
            dummy_hash = salted_hmac(
                key_salt="pretix.plugins.wallet.AppleWalletPass.auth_token",
                algorithm="sha256",
                value=str(12345),
                secret=dummy,
            ).hexdigest()
            constant_time_compare(
                dummy_hash,
                received_token,
            )
            raise AppleWalletPass.DoesNotExist

        if constant_time_compare(
            pass_obj.auth_token,
            received_message,
        ):
            return pass_obj
        else:
            raise AppleWalletPass.DoesNotExist


class AppleWalletPass(models.Model):
    order_position = models.OneToOneField(OrderPosition, on_delete=models.PROTECT)

    serial_number = models.CharField()
    pass_type = models.CharField()
    manifest = models.CharField()
    content = models.FileField()
    updated_at = models.DateTimeField(auto_now=True)

    registered_devices = models.ManyToManyField(
        AppleWalletDevice, related_name="passes"
    )

    objects = AppleWalletPassQuerySet.as_manager()

    class Meta:
        unique_together = [
            ("pass_type", "serial_number"),
        ]

    @property
    def auth_token(self):
        return (
            str(self.order_position.pk)
            + ":"
            + salted_hmac(
                key_salt="pretix.plugins.wallet.AppleWalletPass.auth_token",
                algorithm="sha256",
                secret=self.order_position.web_secret,
                value=str(self.order_position.pk),
            ).hexdigest()
        )


class CombinedAppleWalletPass(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    file = models.FileField(null=True, blank=True, max_length=255)
    created = models.DateTimeField(auto_now_add=True)


class GoogleWalletInstance(models.Model):
    event = models.ForeignKey("pretixbase.Event", on_delete=models.CASCADE)
    order_position = models.ForeignKey(
        OrderPosition, on_delete=models.CASCADE, null=True
    )
    resource = models.CharField()
    identifier = models.CharField()
    data = models.JSONField()
    usages = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("resource", "identifier"),)
