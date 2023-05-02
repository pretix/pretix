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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Enrique Saez, Flavia Bastos, Jakob Schnell, Nics,
# Tobias Kunze, Ture Gjørup, Tydon K
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import calendar
import sys
import uuid
from collections import Counter, OrderedDict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, DecimalException
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import dateutil.parser
from dateutil.tz import datetime_exists
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxLengthValidator, MinValueValidator, RegexValidator,
)
from django.db import models
from django.db.models import Q
from django.utils import formats
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.timezone import is_naive, make_aware, now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_countries.fields import Country
from django_redis import get_redis_connection
from django_scopes import ScopedManager
from i18nfield.fields import I18nCharField, I18nTextField

from pretix.base.models import fields
from pretix.base.models.base import LoggedModel
from pretix.base.models.fields import MultiStringField
from pretix.base.models.tax import TaxedPrice

from ...helpers.images import ImageSizeValidator
from ..media import MEDIA_TYPES
from .event import Event, SubEvent


class ItemCategory(LoggedModel):
    """
    Items can be sorted into these categories.

    :param event: The event this category belongs to
    :type event: Event
    :param name: The name of this category
    :type name: str
    :param position: An integer, used for sorting
    :type position: int
    """
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='categories',
    )
    name = I18nCharField(
        max_length=255,
        verbose_name=_("Category name"),
    )
    internal_name = models.CharField(
        verbose_name=_("Internal name"),
        help_text=_("If you set this, this will be used instead of the public name in the backend."),
        blank=True, null=True, max_length=255
    )
    description = I18nTextField(
        blank=True, verbose_name=_("Category description")
    )
    position = models.IntegerField(
        default=0
    )
    is_addon = models.BooleanField(
        default=False,
        verbose_name=_('Products in this category are add-on products'),
        help_text=_('If selected, the products belonging to this category are not for sale on their own. They can '
                    'only be bought in combination with a product that has this category configured as a possible '
                    'source for add-ons.')
    )

    class Meta:
        verbose_name = _("Product category")
        verbose_name_plural = _("Product categories")
        ordering = ('position', 'id')

    def __str__(self):
        name = self.internal_name or self.name
        if self.is_addon:
            return _('{category} (Add-On products)').format(category=str(name))
        return str(name)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    @property
    def sortkey(self):
        return self.position, self.id

    def __lt__(self, other) -> bool:
        return self.sortkey < other.sortkey


def itempicture_upload_to(instance, filename: str) -> str:
    return 'pub/%s/%s/item-%s-%s.%s' % (
        instance.event.organizer.slug, instance.event.slug, instance.id,
        str(uuid.uuid4()), filename.split('.')[-1]
    )


class SubEventItem(models.Model):
    """
    This model can be used to change the price of a product for a single subevent (i.e. a
    date in an event series).

    :param subevent: The date this belongs to
    :type subevent: SubEvent
    :param item: The item to modify the price for
    :type item: Item
    :param price: The modified price (or ``None`` for the original price)
    :type price: Decimal
    :param disabled: Disable the product for this subevent
    :type disabled: bool
    :param available_until: The date until when the product is on sale
    :type available_until: datetime
    :param available_from: The date this product goes on sale
    :type available_from: datetime
    :param available_until: The date until when the product is on sale
    :type available_until: datetime
    """
    subevent = models.ForeignKey('SubEvent', on_delete=models.CASCADE)
    item = models.ForeignKey('Item', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=13, decimal_places=2, null=True, blank=True)
    disabled = models.BooleanField(default=False, verbose_name=_('Disable product for this date'))
    available_from = models.DateTimeField(
        verbose_name=_("Available from"),
        null=True, blank=True,
        help_text=_('This product will not be sold before the given date.')
    )
    available_until = models.DateTimeField(
        verbose_name=_("Available until"),
        null=True, blank=True,
        help_text=_('This product will not be sold after the given date.')
    )

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.subevent:
            self.subevent.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.subevent:
            self.subevent.event.cache.clear()

    def is_available(self, now_dt: datetime=None) -> bool:
        now_dt = now_dt or now()
        if self.disabled:
            return False
        if self.available_from and self.available_from > now_dt:
            return False
        if self.available_until and self.available_until < now_dt:
            return False
        return True


class SubEventItemVariation(models.Model):
    """
    This model can be used to change the price of a product variation for a single
    subevent (i.e. a date in an event series).

    :param subevent: The date this belongs to
    :type subevent: SubEvent
    :param variation: The variation to modify the price for
    :type variation: ItemVariation
    :param price: The modified price (or ``None`` for the original price)
    :type price: Decimal
    :param disabled: Disable the product for this subevent
    :type disabled: bool
    :param available_until: The date until when the product is on sale
    :type available_until: datetime
    :param available_from: The date this product goes on sale
    :type available_from: datetime
    :param available_until: The date until when the product is on sale
    :type available_until: datetime
    """
    subevent = models.ForeignKey('SubEvent', on_delete=models.CASCADE)
    variation = models.ForeignKey('ItemVariation', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=13, decimal_places=2, null=True, blank=True)
    disabled = models.BooleanField(default=False, verbose_name=_('Disable product for this date'))
    available_from = models.DateTimeField(
        verbose_name=_("Available from"),
        null=True, blank=True,
        help_text=_('This product will not be sold before the given date.')
    )
    available_until = models.DateTimeField(
        verbose_name=_("Available until"),
        null=True, blank=True,
        help_text=_('This product will not be sold after the given date.')
    )

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.subevent:
            self.subevent.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.subevent:
            self.subevent.event.cache.clear()

    def is_available(self, now_dt: datetime=None) -> bool:
        now_dt = now_dt or now()
        if self.disabled:
            return False
        if self.available_from and self.available_from > now_dt:
            return False
        if self.available_until and self.available_until < now_dt:
            return False
        return True


def filter_available(qs, channel='web', voucher=None, allow_addons=False):
    q = (
        # IMPORTANT: If this is updated, also update the ItemVariation query
        # in models/event.py: EventMixin.annotated()
        Q(active=True)
        & Q(Q(available_from__isnull=True) | Q(available_from__lte=now()))
        & Q(Q(available_until__isnull=True) | Q(available_until__gte=now()))
        & Q(sales_channels__contains=channel) & Q(require_bundling=False)
    )
    if not allow_addons:
        q &= Q(Q(category__isnull=True) | Q(category__is_addon=False))

    if voucher:
        if voucher.item_id:
            q &= Q(pk=voucher.item_id)
        elif voucher.quota_id:
            q &= Q(quotas__in=[voucher.quota_id])
    if not voucher or not voucher.show_hidden_items:
        q &= Q(hide_without_voucher=False)

    return qs.filter(q)


class ItemQuerySet(models.QuerySet):
    def filter_available(self, channel='web', voucher=None, allow_addons=False):
        return filter_available(self, channel, voucher, allow_addons)


class ItemQuerySetManager(ScopedManager(organizer='event__organizer').__class__):
    def __init__(self):
        super().__init__()
        self._queryset_class = ItemQuerySet

    def filter_available(self, channel='web', voucher=None, allow_addons=False):
        return filter_available(self.get_queryset(), channel, voucher, allow_addons)


class Item(LoggedModel):
    """
    An item is a thing which can be sold. It belongs to an event and may or may not belong to a category.
    Items are often also called 'products' but are named 'items' internally due to historic reasons.

    :param event: The event this item belongs to
    :type event: Event
    :param category: The category this belongs to. May be null.
    :type category: ItemCategory
    :param name: The name of this item
    :type name: str
    :param active: Whether this item is being sold.
    :type active: bool
    :param description: A short description
    :type description: str
    :param default_price: The item's default price
    :type default_price: decimal.Decimal
    :param tax_rate: The VAT tax that is included in this item's price (in %)
    :type tax_rate: decimal.Decimal
    :param admission: ``True``, if this item allows persons to enter the event (as opposed to e.g. merchandise)
    :type admission: bool
    :param personalized: ``True``, if attendee information should be collected for this ticket
    :type personalized: bool
    :param picture: A product picture to be shown next to the product description
    :type picture: File
    :param available_from: The date this product goes on sale
    :type available_from: datetime
    :param available_until: The date until when the product is on sale
    :type available_until: datetime
    :param require_voucher: If set to ``True``, this item can only be bought using a voucher.
    :type require_voucher: bool
    :param hide_without_voucher: If set to ``True``, this item is only visible and available when a voucher is used.
    :type hide_without_voucher: bool
    :param allow_cancel: If set to ``False``, an order with this product can not be canceled by the user.
    :type allow_cancel: bool
    :param max_per_order: Maximum number of times this item can be in an order. None for unlimited.
    :type max_per_order: int
    :param min_per_order: Minimum number of times this item needs to be in an order if bought at all. None for unlimited.
    :type min_per_order: int
    :param checkin_attention: Requires special attention at check-in
    :type checkin_attention: bool
    :param original_price: The item's "original" price. Will not be used for any calculations, will just be shown.
    :type original_price: decimal.Decimal
    :param require_approval: If set to ``True``, orders containing this product can only be processed and paid after approved by an administrator
    :type require_approval: bool
    :param sales_channels: Sales channels this item is available on.
    :type sales_channels: bool
    :param issue_giftcard: If ``True``, buying this product will give you a gift card with the value of the product's price
    :type issue_giftcard: bool
    :param validity_mode: Instruction how to set ``valid_from``/``valid_until`` on tickets, ``null`` is default event validity.
    :type validity_mode: str
    :param validity_fixed_from: Start of validity if ``validity_mode`` is ``"fixed"``.
    :type validity_fixed_from: datetime
    :param validity_fixed_until: End of validity if ``validity_mode`` is ``"fixed"``.
    :type validity_fixed_until: datetime
    :param validity_dynamic_duration_minutes: Number of minutes if ``validity_mode`` is ``"dnyamic"``.
    :type validity_dynamic_duration_minutes: int
    :param validity_dynamic_duration_hours: Number of hours if ``validity_mode`` is ``"dnyamic"``.
    :type validity_dynamic_duration_hours: int
    :param validity_dynamic_duration_days: Number of days if ``validity_mode`` is ``"dnyamic"``.
    :type validity_dynamic_duration_days: int
    :param validity_dynamic_duration_months: Number of months if ``validity_mode`` is ``"dnyamic"``.
    :type validity_dynamic_duration_months: int
    :param validity_dynamic_start_choice: Whether customers can choose the start date if ``validity_mode`` is ``"dnyamic"``.
    :type validity_dynamic_start_choice: bool
    :param validity_dynamic_start_choice_day_limit: Start date may be maximum this many days in the future if ``validity_mode`` is ``"dnyamic"``.
    :type validity_dynamic_start_choice_day_limnit: int

    """
    VALIDITY_MODE_FIXED = 'fixed'
    VALIDITY_MODE_DYNAMIC = 'dynamic'
    VALIDITY_MODES = (
        (None, _('Event validity (default)')),
        (VALIDITY_MODE_FIXED, _('Fixed time frame')),
        (VALIDITY_MODE_DYNAMIC, _('Dynamic validity')),
    )

    MEDIA_POLICY_REUSE = 'reuse'
    MEDIA_POLICY_NEW = 'new'
    MEDIA_POLICY_REUSE_OR_NEW = 'reuse_or_new'
    MEDIA_POLICIES = (
        (None, _("Don't use re-usable media, use regular one-off tickets")),
        (MEDIA_POLICY_REUSE, _('Require an existing medium to be re-used')),
        (MEDIA_POLICY_NEW, _('Require a previously unknown medium to be newly added')),
        (MEDIA_POLICY_REUSE_OR_NEW, _('Require either an existing or a new medium to be used')),
    )

    objects = ItemQuerySetManager()

    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name=_("Event"),
    )
    category = models.ForeignKey(
        ItemCategory,
        on_delete=models.PROTECT,
        related_name="items",
        blank=True, null=True,
        verbose_name=_("Category"),
        help_text=_("If you have many products, you can optionally sort them into categories to keep things organized.")
    )
    name = I18nCharField(
        max_length=255,
        verbose_name=_("Item name"),
    )
    internal_name = models.CharField(
        verbose_name=_("Internal name"),
        help_text=_("If you set this, this will be used instead of the public name in the backend."),
        blank=True, null=True, max_length=255
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )
    description = I18nTextField(
        verbose_name=_("Description"),
        help_text=_("This is shown below the product name in lists."),
        null=True, blank=True,
    )
    default_price = models.DecimalField(
        verbose_name=_("Default price"),
        help_text=_("If this product has multiple variations, you can set different prices for each of the "
                    "variations. If a variation does not have a special price or if you do not have variations, "
                    "this price will be used."),
        max_digits=13, decimal_places=2, null=True
    )
    free_price = models.BooleanField(
        default=False,
        verbose_name=_("Free price input"),
        help_text=_("If this option is active, your users can choose the price themselves. The price configured above "
                    "is then interpreted as the minimum price a user has to enter. You could use this e.g. to collect "
                    "additional donations for your event. This is currently not supported for products that are "
                    "bought as an add-on to other products.")
    )
    tax_rule = models.ForeignKey(
        'TaxRule',
        verbose_name=_('Sales tax'),
        on_delete=models.PROTECT,
        null=True, blank=True
    )
    admission = models.BooleanField(
        verbose_name=_("Is an admission ticket"),
        help_text=_(
            'Whether or not buying this product allows a person to enter your event'
        ),
        default=False
    )
    personalized = models.BooleanField(
        verbose_name=_("Is a personalized ticket"),
        help_text=_(
            'Whether or not buying this product allows to enter attendee information'
        ),
        default=False
    )
    generate_tickets = models.BooleanField(
        verbose_name=_("Generate tickets"),
        blank=True, null=True,
    )
    allow_waitinglist = models.BooleanField(
        verbose_name=_("Show a waiting list for this ticket"),
        help_text=_("This will only work if waiting lists are enabled for this event."),
        default=True
    )
    show_quota_left = models.BooleanField(
        verbose_name=_("Show number of tickets left"),
        help_text=_("Publicly show how many tickets are still available."),
        blank=True, null=True,
    )
    position = models.IntegerField(
        default=0
    )
    picture = models.ImageField(
        verbose_name=_("Product picture"),
        null=True, blank=True, max_length=255,
        upload_to=itempicture_upload_to,
        validators=[ImageSizeValidator()]
    )
    available_from = models.DateTimeField(
        verbose_name=_("Available from"),
        null=True, blank=True,
        help_text=_('This product will not be sold before the given date.')
    )
    available_until = models.DateTimeField(
        verbose_name=_("Available until"),
        null=True, blank=True,
        help_text=_('This product will not be sold after the given date.')
    )
    hidden_if_available = models.ForeignKey(
        'Quota',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Only show after sellout of"),
        help_text=_("If you select a quota here, this product will only be shown when that quota is "
                    "unavailable. If combined with the option to hide sold-out products, this allows you to "
                    "swap out products for more expensive ones once they are sold out. There might be a short period "
                    "in which both products are visible while all tickets in the referenced quota are reserved, "
                    "but not yet sold.")
    )
    require_voucher = models.BooleanField(
        verbose_name=_('This product can only be bought using a voucher.'),
        default=False,
        help_text=_('To buy this product, the user needs a voucher that applies to this product '
                    'either directly or via a quota.')
    )
    require_approval = models.BooleanField(
        verbose_name=_('Buying this product requires approval'),
        default=False,
        help_text=_('If this product is part of an order, the order will be put into an "approval" state and '
                    'will need to be confirmed by you before it can be paid and completed. You can use this e.g. for '
                    'discounted tickets that are only available to specific groups.'),
    )
    hide_without_voucher = models.BooleanField(
        verbose_name=_('This product will only be shown if a voucher matching the product is redeemed.'),
        default=False,
        help_text=_('This product will be hidden from the event page until the user enters a voucher '
                    'that unlocks this product.')
    )
    require_bundling = models.BooleanField(
        verbose_name=_('Only sell this product as part of a bundle'),
        default=False,
        help_text=_('If this option is set, the product will only be sold as part of bundle products. Do '
                    '<strong>not</strong> check this option if you want to use this product as an add-on product, '
                    'but only for fixed bundles!')
    )
    allow_cancel = models.BooleanField(
        verbose_name=_('Allow product to be canceled or changed'),
        default=True,
        help_text=_('If this is checked, the usual cancellation and order change settings of this event apply. If this is unchecked, '
                    'orders containing this product can not be canceled by users but only by you.')
    )
    min_per_order = models.IntegerField(
        verbose_name=_('Minimum amount per order'),
        null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text=_('This product can only be bought if it is added to the cart at least this many times. If you keep '
                    'the field empty or set it to 0, there is no special limit for this product.')
    )
    max_per_order = models.IntegerField(
        verbose_name=_('Maximum amount per order'),
        null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text=_('This product can only be bought at most this many times within one order. If you keep the field '
                    'empty or set it to 0, there is no special limit for this product. The limit for the maximum '
                    'number of items in the whole order applies regardless.')
    )
    checkin_attention = models.BooleanField(
        verbose_name=_('Requires special attention'),
        default=False,
        help_text=_('If you set this, the check-in app will show a visible warning that this ticket requires special '
                    'attention. You can use this for example for student tickets to indicate to the person at '
                    'check-in that the student ID card still needs to be checked.')
    )
    original_price = models.DecimalField(
        verbose_name=_('Original price'),
        blank=True, null=True,
        max_digits=13, decimal_places=2,
        help_text=_('If set, this will be displayed next to the current price to show that the current price is a '
                    'discounted one. This is just a cosmetic setting and will not actually impact pricing.')
    )
    sales_channels = fields.MultiStringField(
        verbose_name=_('Sales channels'),
        default=['web'],
        blank=True,
    )
    issue_giftcard = models.BooleanField(
        verbose_name=_('This product is a gift card'),
        help_text=_('When a customer buys this product, they will get a gift card with a value corresponding to the '
                    'product price.'),
        default=False
    )
    require_membership = models.BooleanField(
        verbose_name=_('Require a valid membership'),
        default=False,
    )
    require_membership_types = models.ManyToManyField(
        'MembershipType',
        verbose_name=_('Allowed membership types'),
        blank=True,
    )
    require_membership_hidden = models.BooleanField(
        verbose_name=_('Hide without a valid membership'),
        help_text=_('Do not show this unless the customer is logged in and has a valid membership. Be aware that '
                    'this means it will never be visible in the widget.'),
        default=False,
    )
    grant_membership_type = models.ForeignKey(
        'MembershipType',
        null=True, blank=True,
        related_name='granted_by',
        on_delete=models.PROTECT,
        verbose_name=_('This product creates a membership of type'),
    )
    grant_membership_duration_like_event = models.BooleanField(
        verbose_name=_('The duration of the membership is the same as the duration of the event or event series date'),
        default=True,
    )
    grant_membership_duration_days = models.IntegerField(
        verbose_name=_('Membership duration in days'),
        default=0,
    )
    grant_membership_duration_months = models.IntegerField(
        verbose_name=_('Membership duration in months'),
        default=0,
    )

    validity_mode = models.CharField(
        choices=VALIDITY_MODES,
        null=True, blank=True, max_length=16,
        verbose_name=_('Validity'),
        help_text=_(
            'When setting up a regular event, or an event series with time slots, you typically to NOT need to change '
            'this value. The default setting means that the validity time of tickets will not be decided by the '
            'product, but by the event and check-in configuration. Only use the other options if you need them to '
            'realize e.g. a booking of a year-long ticket with a dynamic start date. Note that the validity will be '
            'stored with the ticket, so if you change the settings here later, existing tickets will not be affected '
            'by the change but keep their current validity.'
        )
    )
    validity_fixed_from = models.DateTimeField(null=True, blank=True, verbose_name=_('Start of validity'))
    validity_fixed_until = models.DateTimeField(null=True, blank=True, verbose_name=_('End of validity'))
    validity_dynamic_duration_minutes = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name=_('Minutes'),
    )
    validity_dynamic_duration_hours = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name=_('Hours')
    )
    validity_dynamic_duration_days = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name=_('Days'),
    )
    validity_dynamic_duration_months = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name=_('Months'),
    )
    validity_dynamic_start_choice = models.BooleanField(
        verbose_name=_('Customers can select the validity start date'),
        help_text=_('If not selected, the validity always starts at the time of purchase.'),
        default=False
    )
    validity_dynamic_start_choice_day_limit = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name=_('Maximum future start'),
        help_text=_('The selected start date may only be this many days in the future.')
    )

    media_policy = models.CharField(
        choices=MEDIA_POLICIES,
        null=True, blank=True, max_length=16,
        verbose_name=_('Reusable media policy'),
        help_text=_(
            'If this product should be stored on a re-usable physical medium, you can attach a physical media policy. '
            'This is not required for regular tickets, which just use a one-time barcode, but only for products like '
            'renewable season tickets or re-chargeable gift card wristbands. '
            'This is an advanced feature that also requires specific configuration of ticketing and printing settings.'
        )
    )
    media_type = models.CharField(
        max_length=100,
        null=True, blank=True,
        choices=[(None, _("Don't use re-usable media, use regular one-off tickets"))] + [(k, v) for k, v in MEDIA_TYPES.items()],
        verbose_name=_('Reusable media type'),
        help_text=_(
            'Select the type of physical medium that should be used for this product. Note that not all media types '
            'support all types of products, and not all media types are supported across all sales channels or '
            'check-in processes.'
        )
    )

    # !!! Attention: If you add new fields here, also add them to the copying code in
    # pretix/control/forms/item.py if applicable.

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ("category__position", "category", "position")

    def __str__(self):
        return str(self.internal_name or self.name)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    def delete(self, *args, **kwargs):
        self.vouchers.update(item=None, variation=None, quota=None)
        super().delete(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    @property
    def do_show_quota_left(self):
        if self.show_quota_left is None:
            return self.event.settings.show_quota_left
        return self.show_quota_left

    @property
    def ask_attendee_data(self):
        return self.admission and self.personalized

    def tax(self, price=None, base_price_is='auto', currency=None, invoice_address=None, override_tax_rate=None, include_bundled=False):
        price = price if price is not None else self.default_price

        bundled_sum = Decimal('0.00')
        bundled_sum_net = Decimal('0.00')
        bundled_sum_tax = Decimal('0.00')
        if include_bundled:
            for b in self.bundles.all():
                if b.designated_price and b.bundled_item.tax_rule_id != self.tax_rule_id:
                    if b.bundled_variation:
                        bprice = b.bundled_variation.tax(b.designated_price * b.count,
                                                         base_price_is='gross',
                                                         invoice_address=invoice_address,
                                                         currency=currency)
                    else:
                        bprice = b.bundled_item.tax(b.designated_price * b.count,
                                                    invoice_address=invoice_address,
                                                    base_price_is='gross',
                                                    currency=currency)
                    bundled_sum += bprice.gross
                    bundled_sum_net += bprice.net
                    bundled_sum_tax += bprice.tax

        if not self.tax_rule:
            t = TaxedPrice(gross=price - bundled_sum, net=price - bundled_sum, tax=Decimal('0.00'),
                           rate=Decimal('0.00'), name='')
        else:
            t = self.tax_rule.tax(price, base_price_is=base_price_is, invoice_address=invoice_address,
                                  override_tax_rate=override_tax_rate, currency=currency or self.event.currency,
                                  subtract_from_gross=bundled_sum)

        if bundled_sum:
            t.name = "MIXED!"
            t.gross += bundled_sum
            t.net += bundled_sum_net
            t.tax += bundled_sum_tax

        return t

    def is_available_by_time(self, now_dt: datetime=None) -> bool:
        now_dt = now_dt or now()
        if self.available_from and self.available_from > now_dt:
            return False
        if self.available_until and self.available_until < now_dt:
            return False
        return True

    def is_available(self, now_dt: datetime=None) -> bool:
        """
        Returns whether this item is available according to its ``active`` flag
        and its ``available_from`` and ``available_until`` fields
        """
        now_dt = now_dt or now()
        if not self.active or not self.is_available_by_time(now_dt):
            return False
        return True

    def _get_quotas(self, ignored_quotas=None, subevent=None):
        check_quotas = set(getattr(
            self, '_subevent_quotas',  # Utilize cache in product list
            self.quotas.filter(subevent=subevent).select_related('subevent')
            if subevent else self.quotas.all()
        ))
        if ignored_quotas:
            check_quotas -= set(ignored_quotas)
        return check_quotas

    def check_quotas(self, ignored_quotas=None, count_waitinglist=True, subevent=None, _cache=None,
                     include_bundled=False, trust_parameters=False, fail_on_no_quotas=False):
        """
        This method is used to determine whether this Item is currently available
        for sale.

        :param ignored_quotas: If a collection if quota objects is given here, those
                               quotas will be ignored in the calculation. If this leads
                               to no quotas being checked at all, this method will return
                               unlimited availability.
        :param include_bundled: Also take availability of bundled items into consideration.
        :param trust_parameters: Disable checking of the subevent parameter and disable checking if
                                 any variations exist (performance optimization).
        :returns: any of the return codes of :py:meth:`Quota.availability()`.

        :raises ValueError: if you call this on an item which has variations associated with it.
                            Please use the method on the ItemVariation object you are interested in.
        """
        if not trust_parameters and not subevent and self.event.has_subevents:
            raise TypeError('You need to supply a subevent.')
        check_quotas = self._get_quotas(ignored_quotas=ignored_quotas, subevent=subevent)
        quotacounter = Counter()
        res = Quota.AVAILABILITY_OK, None
        for q in check_quotas:
            quotacounter[q] += 1

        if include_bundled:
            for b in self.bundles.all():
                bundled_check_quotas = (b.bundled_variation or b.bundled_item)._get_quotas(ignored_quotas=ignored_quotas, subevent=subevent)
                if not bundled_check_quotas:
                    return Quota.AVAILABILITY_GONE, 0
                for q in bundled_check_quotas:
                    quotacounter[q] += b.count

        for q, n in quotacounter.items():
            if n == 0:
                continue
            a = q.availability(count_waitinglist=count_waitinglist, _cache=_cache)
            if a[1] is None:
                continue

            num_avail = a[1] // n
            code_avail = Quota.AVAILABILITY_GONE if a[1] >= 1 and num_avail < 1 else a[0]
            # this is not entirely accurate, as it shows "sold out" even if it is actually just "reserved",
            # since we do not know that distinction here if at least one item is available. However, this
            # is only relevant in connection with bundles.

            if code_avail < res[0] or res[1] is None or num_avail < res[1]:
                res = (code_avail, num_avail)

        if len(quotacounter) == 0:
            if fail_on_no_quotas:
                return Quota.AVAILABILITY_GONE, 0
            return Quota.AVAILABILITY_OK, sys.maxsize  # backwards compatibility
        return res

    def allow_delete(self):
        from pretix.base.models.orders import OrderPosition, Transaction

        return not Transaction.objects.filter(item=self).exists() and not OrderPosition.all.filter(item=self).exists()

    @property
    def includes_mixed_tax_rate(self):
        for b in self.bundles.all():
            if b.designated_price and b.bundled_item.tax_rule_id != self.tax_rule_id:
                return True
        return False

    @cached_property
    def has_variations(self):
        return self.variations.exists()

    @staticmethod
    def clean_media_settings(event, media_policy, media_type, issue_giftcard):
        if media_policy:
            if not media_type:
                raise ValidationError(_('If you select a reusable media policy, you also need to select a reusable '
                                        'media type.'))
            mt = MEDIA_TYPES[media_type]
            if not mt.is_active(event.organizer):
                raise ValidationError(_('The selected media type is not enabled in your organizer settings.'))
            if not mt.supports_orderposition and not issue_giftcard:
                raise ValidationError(_('The selected media type does not support usage for tickets currently.'))
            if not mt.supports_giftcard and issue_giftcard:
                raise ValidationError(_('The selected media type does not support usage for gift cards currently.'))
            if issue_giftcard:
                raise ValidationError(_('You currently cannot create gift cards with a reusable media policy. Instead, '
                                        'gift cards for some reusable media types can be created or re-charged directly '
                                        'at the POS.'))

    @staticmethod
    def clean_per_order(min_per_order, max_per_order):
        if min_per_order is not None and max_per_order is not None:
            if min_per_order > max_per_order:
                raise ValidationError(_('The maximum number per order can not be lower than the minimum number per '
                                        'order.'))

    @staticmethod
    def clean_category(category, event):
        if category is not None and category.event is not None and category.event != event:
            raise ValidationError(_('The item\'s category must belong to the same event as the item.'))

    @staticmethod
    def clean_tax_rule(tax_rule, event):
        if tax_rule is not None and tax_rule.event is not None and tax_rule.event != event:
            raise ValidationError(_('The item\'s tax rule must belong to the same event as the item.'))

    @staticmethod
    def clean_available(from_date, until_date):
        if from_date is not None and until_date is not None:
            if from_date > until_date:
                raise ValidationError(_('The item\'s availability cannot end before it starts.'))

    @property
    def meta_data(self):
        data = {p.name: p.default for p in self.event.item_meta_properties.all()}
        if hasattr(self, 'meta_values_cached'):
            data.update({v.property.name: v.value for v in self.meta_values_cached})
        else:
            data.update({v.property.name: v.value for v in self.meta_values.select_related('property').all()})

        return OrderedDict((k, v) for k, v in sorted(data.items(), key=lambda k: k[0]))

    def compute_validity(
        self, *, requested_start: datetime, override_tz=None, enforce_start_limit=False
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        if self.validity_mode == Item.VALIDITY_MODE_FIXED:
            return self.validity_fixed_from, self.validity_fixed_until
        elif self.validity_mode == Item.VALIDITY_MODE_DYNAMIC:
            tz = override_tz or self.event.timezone
            requested_start = requested_start or now()
            if enforce_start_limit and not self.validity_dynamic_start_choice:
                requested_start = now()
            if enforce_start_limit and self.validity_dynamic_start_choice_day_limit is not None:
                requested_start = min(requested_start, now() + timedelta(days=self.validity_dynamic_start_choice_day_limit))

            valid_until = requested_start.astimezone(tz)

            if self.validity_dynamic_duration_months:
                valid_until -= timedelta(days=1)

                replace_day = valid_until.day
                max_day_start_month = calendar.monthrange(valid_until.year, valid_until.month)[1]
                if replace_day == max_day_start_month:
                    # This is a correction for month passes that start e.g. on March 1st – their previous day should
                    # be "last of previous month", not "28th of previous month".
                    replace_day = 31

                replace_year = valid_until.year
                replace_month = valid_until.month + self.validity_dynamic_duration_months

                while replace_month > 12:
                    replace_month -= 12
                    replace_year += 1
                max_day = calendar.monthrange(replace_year, replace_month)[1]
                replace_date = date(
                    year=replace_year,
                    month=replace_month,
                    day=min(replace_day, max_day),
                )
                if self.validity_dynamic_duration_days:
                    replace_date += timedelta(days=self.validity_dynamic_duration_days)
                valid_until = valid_until.replace(
                    year=replace_date.year,
                    month=replace_date.month,
                    day=replace_date.day,
                    hour=23, minute=59, second=59, microsecond=0,
                    tzinfo=tz,
                )
            elif self.validity_dynamic_duration_days:
                replace_date = valid_until.date() + timedelta(days=self.validity_dynamic_duration_days - 1)
                valid_until = valid_until.replace(
                    year=replace_date.year,
                    month=replace_date.month,
                    day=replace_date.day,
                    hour=23, minute=59, second=59, microsecond=0,
                    tzinfo=tz
                )

            if self.validity_dynamic_duration_hours:
                valid_until += timedelta(hours=self.validity_dynamic_duration_hours)

            if self.validity_dynamic_duration_minutes:
                valid_until += timedelta(minutes=self.validity_dynamic_duration_minutes)

            if not datetime_exists(valid_until):
                valid_until += timedelta(hours=1)

            return requested_start, valid_until

        else:
            return None, None


def _all_sales_channels_identifiers():
    from pretix.base.channels import get_all_sales_channels
    return list(get_all_sales_channels().keys())


class ItemVariation(models.Model):
    """
    A variation of a product. For example, if your item is 'T-Shirt'
    then an example for a variation would be 'T-Shirt XL'.

    :param item: The item this variation belongs to
    :type item: Item
    :param value: A string defining this variation
    :type value: str
    :param description: A short description
    :type description: str
    :param active: Whether this variation is being sold.
    :type active: bool
    :param default_price: This variation's default price
    :type default_price: decimal.Decimal
    :param original_price: The item's "original" price. Will not be used for any calculations, will just be shown.
    :type original_price: decimal.Decimal
    :param require_approval: If set to ``True``, orders containing this variation can only be processed and paid after
    approval by an administrator
    :type require_approval: bool

    """
    item = models.ForeignKey(
        Item,
        related_name='variations',
        on_delete=models.CASCADE
    )
    value = I18nCharField(
        max_length=255,
        verbose_name=_('Variation')
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )
    description = I18nTextField(
        verbose_name=_("Description"),
        help_text=_("This is shown below the variation name in lists."),
        null=True, blank=True,
    )
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position")
    )
    default_price = models.DecimalField(
        decimal_places=2, max_digits=13,
        null=True, blank=True,
        verbose_name=_("Default price"),
    )
    original_price = models.DecimalField(
        verbose_name=_('Original price'),
        blank=True, null=True,
        max_digits=13, decimal_places=2,
        help_text=_('If set, this will be displayed next to the current price to show that the current price is a '
                    'discounted one. This is just a cosmetic setting and will not actually impact pricing.')
    )
    require_approval = models.BooleanField(
        verbose_name=_('Require approval'),
        default=False,
        help_text=_('If this variation is part of an order, the order will be put into an "approval" state and '
                    'will need to be confirmed by you before it can be paid and completed. You can use this e.g. for '
                    'discounted tickets that are only available to specific groups.'),
    )
    require_membership = models.BooleanField(
        verbose_name=_('Require a valid membership'),
        default=False,
    )
    require_membership_types = models.ManyToManyField(
        'MembershipType',
        verbose_name=_('Membership types'),
        blank=True,
    )
    require_membership_hidden = models.BooleanField(
        verbose_name=_('Hide without a valid membership'),
        help_text=_('Do not show this unless the customer is logged in and has a valid membership. Be aware that '
                    'this means it will never be visible in the widget.'),
        default=False,
    )
    available_from = models.DateTimeField(
        verbose_name=_("Available from"),
        null=True, blank=True,
        help_text=_('This variation will not be sold before the given date.')
    )
    available_until = models.DateTimeField(
        verbose_name=_("Available until"),
        null=True, blank=True,
        help_text=_('This variation will not be sold after the given date.')
    )
    sales_channels = fields.MultiStringField(
        verbose_name=_('Sales channels'),
        default=_all_sales_channels_identifiers,
        help_text=_('The sales channel selection for the product as a whole takes precedence, so if a sales channel is '
                    'selected here but not on product level, the variation will not be available.'),
        blank=True,
    )
    hide_without_voucher = models.BooleanField(
        verbose_name=_('Show only if a matching voucher is redeemed.'),
        default=False,
        help_text=_('This variation will be hidden from the event page until the user enters a voucher '
                    'that unlocks this variation.')
    )
    checkin_attention = models.BooleanField(
        verbose_name=_('Requires special attention'),
        default=False,
        help_text=_('If you set this, the check-in app will show a visible warning that this ticket requires special '
                    'attention. You can use this for example for student tickets to indicate to the person at '
                    'check-in that the student ID card still needs to be checked.')
    )

    objects = ScopedManager(organizer='item__event__organizer')

    class Meta:
        verbose_name = _("Product variation")
        verbose_name_plural = _("Product variations")
        ordering = ("position", "id")

    def __str__(self):
        return str(self.value)

    @property
    def price(self):
        return self.default_price if self.default_price is not None else self.item.default_price

    def tax(self, price=None, base_price_is='auto', currency=None, include_bundled=False, override_tax_rate=None,
            invoice_address=None):
        price = price if price is not None else self.price

        if not self.item.tax_rule:
            t = TaxedPrice(gross=price, net=price, tax=Decimal('0.00'),
                           rate=Decimal('0.00'), name='')
        else:
            t = self.item.tax_rule.tax(price, base_price_is=base_price_is, currency=currency,
                                       override_tax_rate=override_tax_rate,
                                       invoice_address=invoice_address)

        if include_bundled:
            for b in self.item.bundles.all():
                if b.designated_price and b.bundled_item.tax_rule_id != self.item.tax_rule_id:
                    if b.bundled_variation:
                        bprice = b.bundled_variation.tax(b.designated_price * b.count, base_price_is='gross',
                                                         currency=currency,
                                                         invoice_address=invoice_address)
                    else:
                        bprice = b.bundled_item.tax(b.designated_price * b.count, base_price_is='gross',
                                                    currency=currency,
                                                    invoice_address=invoice_address)
                    compare_price = self.item.tax_rule.tax(b.designated_price * b.count, base_price_is='gross',
                                                           currency=currency, invoice_address=invoice_address)
                    t.net += bprice.net - compare_price.net
                    t.tax += bprice.tax - compare_price.tax
                    t.name = "MIXED!"

        return t

    def delete(self, *args, **kwargs):
        self.vouchers.update(item=None, variation=None, quota=None)
        super().delete(*args, **kwargs)
        if self.item:
            self.item.event.cache.clear()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.item:
            self.item.event.cache.clear()

    def _get_quotas(self, ignored_quotas=None, subevent=None):
        check_quotas = set(getattr(
            self, '_subevent_quotas',  # Utilize cache in product list
            self.quotas.filter(subevent=subevent).select_related('subevent')
            if subevent else self.quotas.all()
        ))
        if ignored_quotas:
            check_quotas -= set(ignored_quotas)
        return check_quotas

    def check_quotas(self, ignored_quotas=None, count_waitinglist=True, subevent=None, _cache=None,
                     include_bundled=False, trust_parameters=False, fail_on_no_quotas=False) -> Tuple[int, int]:
        """
        This method is used to determine whether this ItemVariation is currently
        available for sale in terms of quotas.

        :param ignored_quotas: If a collection if quota objects is given here, those
                               quotas will be ignored in the calculation. If this leads
                               to no quotas being checked at all, this method will return
                               unlimited availability.
        :param count_waitinglist: If ``False``, waiting list entries will be ignored for quota calculation.
        :returns: any of the return codes of :py:meth:`Quota.availability()`.
        """
        if not trust_parameters and not subevent and self.item.event.has_subevents:  # NOQA
            raise TypeError('You need to supply a subevent.')
        check_quotas = self._get_quotas(ignored_quotas=ignored_quotas, subevent=subevent)
        quotacounter = Counter()
        res = Quota.AVAILABILITY_OK, None
        for q in check_quotas:
            quotacounter[q] += 1

        if include_bundled:
            for b in self.item.bundles.all():
                bundled_check_quotas = (b.bundled_variation or b.bundled_item)._get_quotas(ignored_quotas=ignored_quotas, subevent=subevent)
                if not bundled_check_quotas:
                    return Quota.AVAILABILITY_GONE, 0
                for q in bundled_check_quotas:
                    quotacounter[q] += b.count

        for q, n in quotacounter.items():
            a = q.availability(count_waitinglist=count_waitinglist, _cache=_cache)
            if a[1] is None:
                continue

            num_avail = a[1] // n
            code_avail = Quota.AVAILABILITY_GONE if a[1] >= 1 and num_avail < 1 else a[0]
            # this is not entirely accurate, as it shows "sold out" even if it is actually just "reserved",
            # since we do not know that distinction here if at least one item is available. However, this
            # is only relevant in connection with bundles.

            if code_avail < res[0] or res[1] is None or num_avail < res[1]:
                res = (code_avail, num_avail)
        if len(quotacounter) == 0:
            if fail_on_no_quotas:
                return Quota.AVAILABILITY_GONE, 0
            return Quota.AVAILABILITY_OK, sys.maxsize  # backwards compatibility
        return res

    def __lt__(self, other):
        if self.position == other.position:
            return self.id < other.id
        return self.position < other.position

    def allow_delete(self):
        from pretix.base.models.orders import (
            CartPosition, OrderPosition, Transaction,
        )

        return (
            not Transaction.objects.filter(variation=self).exists()
            and not OrderPosition.objects.filter(variation=self).exists()
            and not CartPosition.objects.filter(variation=self).exists()
        )

    def is_only_variation(self):
        return ItemVariation.objects.filter(item=self.item).count() == 1

    def is_available_by_time(self, now_dt: datetime=None) -> bool:
        now_dt = now_dt or now()
        if self.available_from and self.available_from > now_dt:
            return False
        if self.available_until and self.available_until < now_dt:
            return False
        return True

    def is_available(self, now_dt: datetime=None) -> bool:
        """
        Returns whether this item is available according to its ``active`` flag
        and its ``available_from`` and ``available_until`` fields
        """
        now_dt = now_dt or now()
        if not self.active or not self.is_available_by_time(now_dt):
            return False
        return True

    @property
    def meta_data(self):
        data = self.item.meta_data
        if hasattr(self, 'meta_values_cached'):
            data.update({v.property.name: v.value for v in self.meta_values_cached})
        else:
            data.update({v.property.name: v.value for v in self.meta_values.select_related('property').all()})

        return OrderedDict((k, v) for k, v in sorted(data.items(), key=lambda k: k[0]))


class ItemAddOn(models.Model):
    """
    An instance of this model indicates that buying a ticket of the time ``base_item``
    allows you to add up to ``max_count`` items from the category ``addon_category``
    to your order that will be associated with the base item.

    :param base_item: The base item the add-ons are attached to
    :type base_item: Item
    :param addon_category: The category the add-on can be chosen from
    :type addon_category: ItemCategory
    :param min_count: The minimal number of add-ons to be chosen
    :type min_count: int
    :param max_count: The maximal number of add-ons to be chosen
    :type max_count: int
    :param position: An integer used for sorting
    :type position: int
    """
    base_item = models.ForeignKey(
        Item,
        related_name='addons',
        on_delete=models.CASCADE
    )
    addon_category = models.ForeignKey(
        ItemCategory,
        related_name='addon_to',
        verbose_name=_('Category'),
        on_delete=models.CASCADE
    )
    min_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Minimum number')
    )
    max_count = models.PositiveIntegerField(
        default=1,
        verbose_name=_('Maximum number')
    )
    price_included = models.BooleanField(
        default=False,
        verbose_name=_('Add-Ons are included in the price'),
        help_text=_('If selected, adding add-ons to this ticket is free, even if the add-ons would normally cost '
                    'money individually.')
    )
    multi_allowed = models.BooleanField(
        default=False,
        verbose_name=_('Allow the same product to be selected multiple times'),
    )
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position")
    )

    class Meta:
        unique_together = (('base_item', 'addon_category'),)
        ordering = ('position', 'pk')

    def clean(self):
        self.clean_min_count(self.min_count)
        self.clean_max_count(self.max_count)
        self.clean_max_min_count(self.max_count, self.min_count)

    @staticmethod
    def clean_categories(event, item, addon, new_category):
        if event != new_category.event:
            raise ValidationError(_('The add-on\'s category must belong to the same event as the item.'))
        if item is not None:
            if addon is None or addon.addon_category != new_category:
                for addon in item.addons.all():
                    if addon.addon_category == new_category:
                        raise ValidationError(_('The item already has an add-on of this category.'))

    @staticmethod
    def clean_min_count(min_count):
        if min_count < 0:
            raise ValidationError(_('The minimum count needs to be equal to or greater than zero.'))

    @staticmethod
    def clean_max_count(max_count):
        if max_count < 0:
            raise ValidationError(_('The maximum count needs to be equal to or greater than zero.'))

    @staticmethod
    def clean_max_min_count(max_count, min_count):
        if max_count < min_count:
            raise ValidationError(_('The maximum count needs to be greater than the minimum count.'))


class ItemBundle(models.Model):
    """
    An instance of this model indicates that buying a ticket of the type ``base_item``
    automatically also buys ``count`` items of type ``bundled_item``.

    :param base_item: The base item the bundle is attached to
    :type base_item: Item
    :param bundled_item: The bundled item
    :type bundled_item: Item
    :param bundled_variation: The variation, if the bundled item has variations
    :type bundled_variation: ItemVariation
    :param count: The number of items to bundle
    :type count: int
    :param designated_price: The designated part price (optional)
    :type designated_price: bool
    """
    base_item = models.ForeignKey(
        Item,
        related_name='bundles',
        on_delete=models.CASCADE
    )
    bundled_item = models.ForeignKey(
        Item,
        related_name='bundled_with',
        verbose_name=_('Bundled item'),
        on_delete=models.CASCADE
    )
    bundled_variation = models.ForeignKey(
        ItemVariation,
        related_name='bundled_with',
        verbose_name=_('Bundled variation'),
        null=True, blank=True,
        on_delete=models.CASCADE
    )
    count = models.PositiveIntegerField(
        default=1,
        verbose_name=_('Quantity')
    )
    designated_price = models.DecimalField(
        default=Decimal('0.00'), blank=True,
        decimal_places=2, max_digits=13,
        verbose_name=_('Designated price part'),
        help_text=_('If set, it will be shown that this bundled item is responsible for the given value of the total '
                    'gross price. This might be important in cases of mixed taxation, but can be kept blank otherwise. This '
                    'value will NOT be added to the base item\'s price.')
    )

    def clean(self):
        self.clean_count(self.count)

    def describe(self):
        if self.count == 1:
            if self.bundled_variation_id:
                return "{} – {}".format(self.bundled_item.name, self.bundled_variation.value)
            else:
                return self.bundled_item.name
        else:
            if self.bundled_variation_id:
                return "{}× {} – {}".format(self.count, self.bundled_item.name, self.bundled_variation.value)
            else:
                return "{}x {}".format(self.count, self.bundled_item.name)

    @staticmethod
    def clean_itemvar(event, bundled_item, bundled_variation):
        if event != bundled_item.event:
            raise ValidationError(_('The bundled item must belong to the same event as the item.'))
        if bundled_item.has_variations and not bundled_variation:
            raise ValidationError(_('A variation needs to be set for this item.'))
        if bundled_variation and bundled_variation.item != bundled_item:
            raise ValidationError(_('The chosen variation does not belong to this item.'))

    @staticmethod
    def clean_count(count):
        if count < 0:
            raise ValidationError(_('The count needs to be equal to or greater than zero.'))


class Question(LoggedModel):
    """
    A question is an input field that can be used to extend a ticket by custom information,
    e.g. "Attendee age". The answers are found next to the position. The answers may be found
    in QuestionAnswers, attached to OrderPositions/CartPositions. A question can allow one of
    several input types, currently:

    * a number (``TYPE_NUMBER``)
    * a one-line string (``TYPE_STRING``)
    * a multi-line string (``TYPE_TEXT``)
    * a boolean (``TYPE_BOOLEAN``)
    * a multiple choice option (``TYPE_CHOICE`` and ``TYPE_CHOICE_MULTIPLE``)
    * a file upload (``TYPE_FILE``)
    * a date (``TYPE_DATE``)
    * a time (``TYPE_TIME``)
    * a date and a time (``TYPE_DATETIME``)

    :param event: The event this question belongs to
    :type event: Event
    :param question: The question text. This will be displayed next to the input field.
    :type question: str
    :param type: One of the above types
    :param required: Whether answering this question is required for submitting an order including
                     items associated with this question.
    :type required: bool
    :param items: A set of ``Items`` objects that this question should be applied to
    :param ask_during_checkin: Whether to ask this question during check-in instead of during check-out.
    :type ask_during_checkin: bool
    :param hidden: Whether to only show the question in the backend
    :type hidden: bool
    :param identifier: An arbitrary, internal identifier
    :type identifier: str
    :param dependency_question: This question will only show up if the referenced question is set to `dependency_value`.
    :type dependency_question: Question
    :param dependency_values: The values that `dependency_question` needs to be set to for this question to be applicable.
    :type dependency_values: list[str]
    """
    TYPE_NUMBER = "N"
    TYPE_STRING = "S"
    TYPE_TEXT = "T"
    TYPE_BOOLEAN = "B"
    TYPE_CHOICE = "C"
    TYPE_CHOICE_MULTIPLE = "M"
    TYPE_FILE = "F"
    TYPE_DATE = "D"
    TYPE_TIME = "H"
    TYPE_DATETIME = "W"
    TYPE_COUNTRYCODE = "CC"
    TYPE_PHONENUMBER = "TEL"
    TYPE_CHOICES = (
        (TYPE_NUMBER, _("Number")),
        (TYPE_STRING, _("Text (one line)")),
        (TYPE_TEXT, _("Multiline text")),
        (TYPE_BOOLEAN, _("Yes/No")),
        (TYPE_CHOICE, _("Choose one from a list")),
        (TYPE_CHOICE_MULTIPLE, _("Choose multiple from a list")),
        (TYPE_FILE, _("File upload")),
        (TYPE_DATE, _("Date")),
        (TYPE_TIME, _("Time")),
        (TYPE_DATETIME, _("Date and time")),
        (TYPE_COUNTRYCODE, _("Country code (ISO 3166-1 alpha-2)")),
        (TYPE_PHONENUMBER, _("Phone number")),
    )
    UNLOCALIZED_TYPES = [TYPE_DATE, TYPE_TIME, TYPE_DATETIME]
    ASK_DURING_CHECKIN_UNSUPPORTED = [TYPE_PHONENUMBER]

    event = models.ForeignKey(
        Event,
        related_name="questions",
        on_delete=models.CASCADE
    )
    question = I18nTextField(
        verbose_name=_("Question")
    )
    identifier = models.CharField(
        max_length=190,
        verbose_name=_("Internal identifier"),
        help_text=_('You can enter any value here to make it easier to match the data with other sources. If you do '
                    'not input one, we will generate one automatically.'),
        validators=[
            RegexValidator(
                regex=r"^[a-zA-Z0-9.\-_]+$",
                message=_("The identifier may only contain letters, numbers, dots, dashes, and underscores."),
            ),
        ],
    )
    help_text = I18nTextField(
        verbose_name=_("Help text"),
        help_text=_("If the question needs to be explained or clarified, do it here!"),
        null=True, blank=True,
    )
    type = models.CharField(
        max_length=5,
        choices=TYPE_CHOICES,
        verbose_name=_("Question type")
    )
    required = models.BooleanField(
        default=False,
        verbose_name=_("Required question")
    )
    items = models.ManyToManyField(
        Item,
        related_name='questions',
        verbose_name=_("Products"),
        blank=True,
        help_text=_('This question will be asked to buyers of the selected products')
    )
    position = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Position")
    )
    ask_during_checkin = models.BooleanField(
        verbose_name=_('Ask during check-in instead of in the ticket buying process'),
        help_text=_('Not supported by all check-in apps for all question types.'),
        default=False
    )
    hidden = models.BooleanField(
        verbose_name=_('Hidden question'),
        help_text=_('This question will only show up in the backend.'),
        default=False
    )
    print_on_invoice = models.BooleanField(
        verbose_name=_('Print answer on invoices'),
        default=False
    )
    dependency_question = models.ForeignKey(
        'Question', null=True, blank=True, on_delete=models.SET_NULL, related_name='dependent_questions'
    )
    dependency_values = MultiStringField(default=[])
    valid_number_min = models.DecimalField(decimal_places=6, max_digits=16, null=True, blank=True,
                                           verbose_name=_('Minimum value'),
                                           help_text=_('Currently not supported in our apps and during check-in'))
    valid_number_max = models.DecimalField(decimal_places=6, max_digits=16, null=True, blank=True,
                                           verbose_name=_('Maximum value'),
                                           help_text=_('Currently not supported in our apps and during check-in'))
    valid_date_min = models.DateField(null=True, blank=True,
                                      verbose_name=_('Minimum value'),
                                      help_text=_('Currently not supported in our apps and during check-in'))
    valid_date_max = models.DateField(null=True, blank=True,
                                      verbose_name=_('Maximum value'),
                                      help_text=_('Currently not supported in our apps and during check-in'))
    valid_datetime_min = models.DateTimeField(null=True, blank=True,
                                              verbose_name=_('Minimum value'),
                                              help_text=_('Currently not supported in our apps and during check-in'))
    valid_datetime_max = models.DateTimeField(null=True, blank=True,
                                              verbose_name=_('Maximum value'),
                                              help_text=_('Currently not supported in our apps and during check-in'))
    valid_string_length_max = models.PositiveIntegerField(null=True, blank=True,
                                                          verbose_name=_('Maximum length'),
                                                          help_text=_(
                                                              'Currently not supported in our apps and during check-in'
                                                          ))
    valid_file_portrait = models.BooleanField(
        default=False,
        verbose_name=_('Validate file to be a portrait'),
        help_text=_('If checked, files must be images with an aspect ratio of 3:4. This is commonly used for photos '
                    'printed on badges.')
    )

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")
        ordering = ('position', 'id')
        unique_together = (('event', 'identifier'),)

    def __str__(self):
        return str(self.question)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    def clean_identifier(self, code):
        Question._clean_identifier(self.event, code, self)

    @staticmethod
    def _clean_identifier(event, code, instance=None):
        qs = Question.objects.filter(event=event, identifier__iexact=code)
        if instance and instance.pk:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise ValidationError(_('This identifier is already used for a different question.'))

    def save(self, *args, **kwargs):
        if not self.identifier:
            charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
            while True:
                code = get_random_string(length=8, allowed_chars=charset)
                if not Question.objects.filter(event=self.event, identifier=code).exists():
                    self.identifier = code
                    break
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'identifier'}.union(kwargs['update_fields'])
        super().save(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    @property
    def sortkey(self):
        return self.position, self.id

    def __lt__(self, other) -> bool:
        return self.sortkey < other.sortkey

    def clean_answer(self, answer):
        if self.required:
            if not answer or (self.type == Question.TYPE_BOOLEAN and answer not in ("true", "True", True)):
                raise ValidationError(_('An answer to this question is required to proceed.'))
        if not answer:
            if self.type == Question.TYPE_BOOLEAN:
                return False
            return None

        if self.type == Question.TYPE_CHOICE:
            if isinstance(answer, QuestionOption):
                return answer
            if not isinstance(answer, (int, str)):
                raise ValidationError(_('Invalid input type.'))
            q = Q(identifier=answer)
            if isinstance(answer, int) or (isinstance(answer, str) and answer.isdigit()):
                q |= Q(pk=answer)
            o = self.options.filter(q).first()
            if not o:
                raise ValidationError(_('Invalid option selected.'))
            return o
        elif self.type == Question.TYPE_CHOICE_MULTIPLE:
            if isinstance(answer, str):
                l_ = list(self.options.filter(
                    Q(pk__in=[a for a in answer.split(",") if a.isdigit()]) |
                    Q(identifier__in=answer.split(","))
                ))
                llen = len(answer.split(','))
            elif all(isinstance(o, QuestionOption) for o in answer):
                return o
            else:
                l_ = list(self.options.filter(
                    Q(pk__in=[a for a in answer if isinstance(a, int) or a.isdigit()]) |
                    Q(identifier__in=answer)
                ))
                llen = len(answer)
            if len(l_) != llen:
                raise ValidationError(_('Invalid option selected.'))
            return l_
        elif self.type == Question.TYPE_BOOLEAN:
            return answer in ('true', 'True', True)
        elif self.type == Question.TYPE_NUMBER:
            answer = formats.sanitize_separators(answer)
            answer = str(answer).strip()
            try:
                v = Decimal(answer)
                if self.valid_number_min is not None and v < self.valid_number_min:
                    raise ValidationError(_('The number is to low.'))
                if self.valid_number_max is not None and v > self.valid_number_max:
                    raise ValidationError(_('The number is to high.'))
                return v
            except DecimalException:
                raise ValidationError(_('Invalid number input.'))
        elif self.type == Question.TYPE_DATE:
            if isinstance(answer, date):
                return answer
            try:
                dt = dateutil.parser.parse(answer).date()
                if self.valid_date_min is not None and dt < self.valid_date_min:
                    raise ValidationError(_('Please choose a later date.'))
                if self.valid_date_max is not None and dt > self.valid_date_max:
                    raise ValidationError(_('Please choose an earlier date.'))
                return dt
            except:
                raise ValidationError(_('Invalid date input.'))
        elif self.type == Question.TYPE_TIME:
            if isinstance(answer, time):
                return answer
            try:
                return dateutil.parser.parse(answer).time()
            except:
                raise ValidationError(_('Invalid time input.'))
        elif self.type == Question.TYPE_DATETIME and answer:
            if isinstance(answer, datetime):
                return answer
            try:
                dt = dateutil.parser.parse(answer)
                if is_naive(dt):
                    dt = make_aware(dt, ZoneInfo(self.event.settings.timezone))
            except:
                raise ValidationError(_('Invalid datetime input.'))
            else:
                if self.valid_datetime_min is not None and dt < self.valid_datetime_min:
                    raise ValidationError(_('Please choose a later date.'))
                if self.valid_datetime_max is not None and dt > self.valid_datetime_max:
                    raise ValidationError(_('Please choose an earlier date.'))
                return dt
        elif self.type == Question.TYPE_COUNTRYCODE and answer:
            c = Country(answer.upper())
            if c.name:
                return answer
            else:
                raise ValidationError(_('Unknown country code.'))
        elif self.type in (Question.TYPE_STRING, Question.TYPE_TEXT):
            if self.valid_string_length_max is not None and len(answer) > self.valid_string_length_max:
                raise ValidationError(MaxLengthValidator.message % {
                    'limit_value': self.valid_string_length_max,
                    'show_value': len(answer)
                })

        return answer

    @staticmethod
    def clean_items(event, items):
        for item in items:
            if event != item.event:
                raise ValidationError(_('One or more items do not belong to this event.'))


class QuestionOption(models.Model):
    question = models.ForeignKey('Question', related_name='options', on_delete=models.CASCADE)
    identifier = models.CharField(
        max_length=190,
        help_text=_('You can enter any value here to make it easier to match the data with other sources. If you do '
                    'not input one, we will generate one automatically.'),
        validators=[
            RegexValidator(
                regex=r"^[a-zA-Z0-9.\-_]+$",
                message=_("The identifier may only contain letters, numbers, dots, dashes, and underscores."),
            ),
        ],
    )
    answer = I18nCharField(verbose_name=_('Answer'))
    position = models.IntegerField(default=0)

    def __str__(self):
        return str(self.answer)

    def save(self, *args, **kwargs):
        if not self.identifier:
            charset = list('ABCDEFGHJKLMNPQRSTUVWXYZ3789')
            while True:
                code = get_random_string(length=8, allowed_chars=charset)
                if not QuestionOption.objects.filter(question__event=self.question.event, identifier=code).exists():
                    self.identifier = code
                    break
            if 'update_fields' in kwargs:
                kwargs['update_fields'] = {'identifier'}.union(kwargs['update_fields'])
        super().save(*args, **kwargs)

    @staticmethod
    def clean_identifier(event, code, instance=None, known=[]):
        qs = QuestionOption.objects.filter(question__event=event, identifier=code)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists() or code in known:
            raise ValidationError(_('The identifier "{}" is already used for a different option.').format(code))

    class Meta:
        verbose_name = _("Question option")
        verbose_name_plural = _("Question options")
        ordering = ('position', 'id')


class Quota(LoggedModel):
    """
    A quota is a "pool of tickets". It is there to limit the number of items
    of a certain type to be sold. For example, you could have a quota of 500
    applied to all of your items (because you only have that much space in your
    venue), and also a quota of 100 applied to the VIP tickets for exclusivity.
    In this case, no more than 500 tickets will be sold in total and no more
    than 100 of them will be VIP tickets (but 450 normal and 50 VIP tickets
    will be fine).

    As always, a quota can not only be tied to an item, but also to specific
    variations.

    Please read the documentation section on quotas carefully before doing
    anything with quotas. This might confuse you otherwise.
    https://docs.pretix.eu/en/latest/development/concepts.html#quotas

    The AVAILABILITY_* constants represent various states of a quota allowing
    its items/variations to be up for sale.

    AVAILABILITY_OK
        This item is available for sale.

    AVAILABILITY_RESERVED
        This item is currently not available for sale because all available
        items are in people's shopping carts. It might become available
        again if those people do not proceed to the checkout.

    AVAILABILITY_ORDERED
        This item is currently not available for sale because all available
        items are ordered. It might become available again if those people
        do not pay.

    AVAILABILITY_GONE
        This item is completely sold out.

    :param event: The event this belongs to
    :type event: Event
    :param subevent: The event series date this belongs to, if event series are enabled
    :type subevent: SubEvent
    :param name: This quota's name
    :type name: str
    :param size: The number of items in this quota
    :type size: int
    :param items: The set of :py:class:`Item` objects this quota applies to
    :param variations: The set of :py:class:`ItemVariation` objects this quota applies to

    This model keeps a cache of the quota availability that is used in places where up-to-date
    data is not important. This cache might be out of date even though a more recent quota was
    calculated. This is intentional to keep database writes low. Currently, the cached values
    are written whenever the quota is being calculated throughout the system and the cache is
    at least 120 seconds old or if the new value is qualitatively "better" than the cached one
    (i.e. more free quota).

    There's also a cronjob that refreshes the cache of every quota if there is any log entry in
    the event that is newer than the quota's cached time.
    """

    AVAILABILITY_GONE = 0
    AVAILABILITY_ORDERED = 10
    AVAILABILITY_RESERVED = 20
    AVAILABILITY_OK = 100

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="quotas",
        verbose_name=_("Event"),
    )
    subevent = models.ForeignKey(
        SubEvent,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="quotas",
        verbose_name=pgettext_lazy('subevent', "Date"),
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Name")
    )
    size = models.PositiveIntegerField(
        verbose_name=_("Total capacity"),
        null=True, blank=True,
        help_text=_("Leave empty for an unlimited number of tickets.")
    )
    items = models.ManyToManyField(
        Item,
        verbose_name=_("Item"),
        related_name="quotas",
        blank=True
    )
    variations = models.ManyToManyField(
        ItemVariation,
        related_name="quotas",
        blank=True,
        verbose_name=_("Variations")
    )

    ignore_for_event_availability = models.BooleanField(
        verbose_name=_('Ignore this quota when determining event availability'),
        help_text=_('If you enable this, this quota will be ignored when determining event availability in your event calendar. '
                    'This is useful e.g. for merchandise that is added to each event but should not stop the event from being shown '
                    'as sold out.'),
        default=False,
    )

    close_when_sold_out = models.BooleanField(
        verbose_name=_('Close this quota permanently once it is sold out'),
        help_text=_('If you enable this, when the quota is sold out once, no more tickets will be sold, '
                    'even if tickets become available again through cancellations or expiring orders. Of course, '
                    'you can always re-open it manually.'),
        default=False
    )
    closed = models.BooleanField(default=False)

    release_after_exit = models.BooleanField(
        verbose_name=_('Allow to sell more tickets once people have checked out'),
        help_text=_('With this option, quota will be released as soon as people are scanned at an exit of your event. '
                    'This will only happen if they have been scanned both at an entry and at an exit and the exit '
                    'is the more recent scan. It does not matter which check-in list either of the scans was on, '
                    'but check-in lists are ignored if they are set to "Allow re-entering after an exit scan" to '
                    'prevent accidental overbooking.'),
        default=False,
    )

    objects = ScopedManager(organizer='event__organizer')

    class Meta:
        verbose_name = _("Quota")
        verbose_name_plural = _("Quotas")
        ordering = ('name',)

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        self.vouchers.update(item=None, variation=None, quota=None)
        super().delete(*args, **kwargs)
        if self.event:
            self.event.cache.clear()

    def save(self, *args, **kwargs):
        # This is *not* called when the db-level cache is upated, since we use bulk_update there
        clear_cache = kwargs.pop('clear_cache', True)
        super().save(*args, **kwargs)
        if self.event and clear_cache:
            self.event.cache.clear()

    def rebuild_cache(self, now_dt=None):
        if settings.HAS_REDIS:
            rc = get_redis_connection("redis")
            rc.hdel(f'quotas:{self.event_id}:availabilitycache', str(self.pk))
            self.availability(now_dt=now_dt)

    def availability(
            self, now_dt: datetime=None, count_waitinglist=True, _cache=None, allow_cache=False
    ) -> Tuple[int, int]:
        """
        This method is used to determine whether Items or ItemVariations belonging
        to this quota should currently be available for sale.

        :param count_waitinglist: Whether or not take waiting list reservations into account. Defaults
                                  to ``True``.
        :param _cache: A dictionary mapping quota IDs to availabilities. If this quota is already
                       contained in that dictionary, this value will be used. Otherwise, the dict
                       will be populated accordingly.
        :param allow_cache: Allow for values to be returned from the longer-term cache, see also
                            the documentation of this model class. Only works if ``count_waitinglist`` is
                            set to ``True``.

        :returns: a tuple where the first entry is one of the ``Quota.AVAILABILITY_`` constants
                  and the second is the number of available tickets.
        """
        from ..services.quotas import QuotaAvailability

        if _cache and count_waitinglist is not _cache.get('_count_waitinglist', True):
            _cache.clear()

        if _cache is not None and self.pk in _cache:
            return _cache[self.pk]
        qa = QuotaAvailability(count_waitinglist=count_waitinglist, early_out=False)
        qa.queue(self)
        qa.compute(now_dt=now_dt, allow_cache=allow_cache)
        res = qa.results[self]

        if _cache is not None:
            _cache[self.pk] = res
            _cache['_count_waitinglist'] = count_waitinglist
        return res

    class QuotaExceededException(Exception):
        pass

    @staticmethod
    def clean_variations(items, variations):
        for variation in (variations or []):
            if variation.item not in items:
                raise ValidationError(_('All variations must belong to an item contained in the items list.'))

    @staticmethod
    def clean_items(event, items, variations):
        if not items:
            return
        for item in items:
            if event != item.event:
                raise ValidationError(_('One or more items do not belong to this event.'))
            if item.has_variations:
                if not variations or not any(var.item == item for var in variations):
                    raise ValidationError(_('One or more items has variations but none of these are in the variations list.'))

    @staticmethod
    def clean_subevent(event, subevent):
        if event.has_subevents:
            if not subevent:
                raise ValidationError(_('Subevent cannot be null for event series.'))
            if event != subevent.event:
                raise ValidationError(_('The subevent does not belong to this event.'))
        else:
            if subevent:
                raise ValidationError(_('The subevent does not belong to this event.'))


class ItemMetaProperty(LoggedModel):
    """
    An event can have ItemMetaProperty objects attached to define meta information fields
    for its items. This information can be re-used for example in ticket layouts.

    :param event: The event this property is defined for.
    :type event: Event
    :param name: Name
    :type name: Name of the property, used in various places
    :param default: Default value
    :type default: str
    """
    event = models.ForeignKey(Event, related_name="item_meta_properties", on_delete=models.CASCADE)
    name = models.CharField(
        max_length=50, db_index=True,
        help_text=_(
            "Can not contain spaces or special characters except underscores"
        ),
        validators=[
            RegexValidator(
                regex="^[a-zA-Z0-9_]+$",
                message=_("The property name may only contain letters, numbers and underscores."),
            ),
        ],
        verbose_name=_("Name"),
    )
    default = models.TextField(blank=True)
    required = models.BooleanField(
        default=False, verbose_name=_("Required for products"),
        help_text=_("If checked, this property must be set in each product. Does not apply if a default value is set.")
    )
    allowed_values = models.TextField(
        null=True, blank=True,
        verbose_name=_("Valid values"),
        help_text=_("If you keep this empty, any value is allowed. Otherwise, enter one possible value per line.")
    )

    class Meta:
        ordering = ("name",)


class ItemMetaValue(LoggedModel):
    """
    A meta-data value assigned to an item.

    :param item: The item this metadata is valid for
    :type item: Item
    :param property: The property this value belongs to
    :type property: ItemMetaProperty
    :param value: The actual value
    :type value: str
    """
    item = models.ForeignKey('Item', on_delete=models.CASCADE, related_name='meta_values')
    property = models.ForeignKey('ItemMetaProperty', on_delete=models.CASCADE, related_name='item_values')
    value = models.TextField()

    class Meta:
        unique_together = ('item', 'property')


class ItemVariationMetaValue(LoggedModel):
    """
    A meta-data value assigned to an item variation, overriding the value on the item.

    :param variation: The variation this metadata is valid for
    :type variation: ItemVariation
    :param property: The property this value belongs to
    :type property: ItemMetaProperty
    :param value: The actual value
    :type value: str
    """
    variation = models.ForeignKey('ItemVariation', on_delete=models.CASCADE, related_name='meta_values')
    property = models.ForeignKey('ItemMetaProperty', on_delete=models.CASCADE, related_name='variation_values')
    value = models.TextField()

    class Meta:
        unique_together = ('variation', 'property')
