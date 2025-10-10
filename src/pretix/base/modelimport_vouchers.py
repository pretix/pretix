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
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.utils.functional import cached_property
from django.utils.translation import gettext as _, gettext_lazy, pgettext_lazy

from pretix.base.modelimport import (
    BooleanColumnMixin, DatetimeColumnMixin, DecimalColumnMixin, ImportColumn,
    IntegerColumnMixin, SubeventColumnMixin, i18n_flat,
)
from pretix.base.models import ItemVariation, Quota, Seat, SubEvent, Voucher
from pretix.base.signals import voucher_import_columns


class CodeColumn(ImportColumn):
    identifier = 'code'
    verbose_name = gettext_lazy('Voucher code')
    default_value = None

    def __init__(self, *args):
        self._cached = set()
        super().__init__(*args)

    def clean(self, value, previous_values):
        if value:
            MinLengthValidator(5)(value)
        if value and (value in self._cached or Voucher.objects.filter(event=self.event, code=value).exists()):
            raise ValidationError(_('A voucher with this code already exists.'))
        self._cached.add(value)
        return value

    def assign(self, value, obj: Voucher, **kwargs):
        obj.code = value


class SubeventColumn(SubeventColumnMixin, ImportColumn):
    identifier = 'subevent'
    verbose_name = pgettext_lazy('subevents', 'Date')

    def assign(self, value, obj: SubEvent, **kwargs):
        obj.subevent = value


class MaxUsagesColumn(IntegerColumnMixin, ImportColumn):
    identifier = 'max_usages'
    verbose_name = gettext_lazy('Maximum usages')
    default_value = None
    initial = "static:1"

    def static_choices(self):
        return [
            ("1", "1")
        ]

    def clean(self, value, previous_values):
        if value is None and previous_values.get("code"):
            raise ValidationError(_('The maximum number of usages must be set.'))
        return super().clean(value, previous_values)

    def assign(self, value, obj: Voucher, **kwargs):
        obj.max_usages = value if value is not None else 1


class MinUsagesColumn(IntegerColumnMixin, ImportColumn):
    identifier = 'min_usages'
    verbose_name = gettext_lazy('Minimum usages')
    default_value = None
    initial = "static:1"

    def static_choices(self):
        return [
            ("1", "1")
        ]

    def assign(self, value, obj: Voucher, **kwargs):
        obj.min_usages = value if value is not None else 1


class BudgetColumn(DecimalColumnMixin, ImportColumn):
    identifier = 'budget'
    verbose_name = gettext_lazy('Maximum discount budget')

    def assign(self, value, obj: Voucher, **kwargs):
        obj.budget = value


class ValidUntilColumn(DatetimeColumnMixin, ImportColumn):
    identifier = 'valid_until'
    verbose_name = gettext_lazy('Valid until')

    def assign(self, value, obj: Voucher, **kwargs):
        obj.valid_until = value


class BlockQuotaColumn(BooleanColumnMixin, ImportColumn):
    identifier = 'block_quota'
    verbose_name = gettext_lazy('Reserve ticket from quota')

    def assign(self, value, obj: Voucher, **kwargs):
        obj.block_quota = value


class AllowIgnoreQuotaColumn(BooleanColumnMixin, ImportColumn):
    identifier = 'allow_ignore_quota'
    verbose_name = gettext_lazy('Allow to bypass quota')

    def assign(self, value, obj: Voucher, **kwargs):
        obj.allow_ignore_quota = value


class PriceModeColumn(ImportColumn):
    identifier = 'price_mode'
    verbose_name = gettext_lazy('Price mode')
    default_value = None
    initial = 'static:none'

    def static_choices(self):
        return Voucher.PRICE_MODES

    def clean(self, value, previous_values):
        d = dict(Voucher.PRICE_MODES)
        reverse = {v: k for k, v in Voucher.PRICE_MODES}
        if value in d:
            return value
        elif value in reverse:
            return reverse[value]
        else:
            raise ValidationError(_("Could not parse {value} as a price mode, use one of {options}.").format(
                value=value, options=', '.join(d.keys())
            ))

    def assign(self, value, voucher: Voucher, **kwargs):
        voucher.price_mode = value


class ValueColumn(DecimalColumnMixin, ImportColumn):
    identifier = 'value'
    verbose_name = gettext_lazy('Voucher value')

    def clean(self, value, previous_values):
        value = super().clean(value, previous_values)
        if value and previous_values.get("price_mode") == "none":
            raise ValidationError(_("It is pointless to set a value without a price mode."))
        return value

    def assign(self, value, obj: Voucher, **kwargs):
        obj.value = value or Decimal("0.00")


class ItemColumn(ImportColumn):
    identifier = 'item'
    verbose_name = gettext_lazy('Product')

    @cached_property
    def items(self):
        return list(self.event.items.filter(active=True))

    def static_choices(self):
        return [
            (str(p.pk), str(p)) for p in self.items
        ]

    def clean(self, value, previous_values):
        if not value:
            return
        matches = [
            p for p in self.items
            if str(p.pk) == value or (p.internal_name and p.internal_name == value) or any(
                (v and v == value) for v in i18n_flat(p.name))
        ]
        if len(matches) == 0:
            raise ValidationError(_("No matching product was found."))
        if len(matches) > 1:
            raise ValidationError(_("Multiple matching products were found."))
        return matches[0]

    def assign(self, value, voucher, **kwargs):
        voucher.item = value


class VariationColumn(ImportColumn):
    identifier = 'variation'
    verbose_name = gettext_lazy('Product variation')

    @cached_property
    def items(self):
        return list(ItemVariation.objects.filter(
            active=True, item__active=True, item__event=self.event
        ).select_related('item'))

    def static_choices(self):
        return [
            (str(p.pk), '{} – {}'.format(p.item, p.value)) for p in self.items
        ]

    def clean(self, value, previous_values):
        if value:
            matches = [
                p for p in self.items
                if (str(p.pk) == value or any((v and v == value) for v in i18n_flat(p.value))) and p.item_id == previous_values['item'].pk
            ]
            if len(matches) == 0:
                raise ValidationError(_("No matching variation was found."))
            if len(matches) > 1:
                raise ValidationError(_("Multiple matching variations were found."))
            return matches[0]
        return value

    def assign(self, value, voucher: Voucher, **kwargs):
        voucher.variation = value


class QuotaColumn(ImportColumn):
    identifier = 'quota'
    verbose_name = gettext_lazy('Quota')

    @cached_property
    def quotas(self):
        return list(Quota.objects.filter(
            event=self.event
        ))

    def static_choices(self):
        return [
            (str(q.pk), q.name) for q in self.quotas
        ]

    def clean(self, value, previous_values):
        if value:
            if previous_values.get('item'):
                raise ValidationError(_("You cannot specify a quota if you specified a product."))
            matches = [
                q for q in self.quotas
                if str(q.pk) == value or q.name == value
            ]
            if len(matches) == 0:
                raise ValidationError(_("No matching variation was found."))
            if len(matches) > 1:
                raise ValidationError(_("Multiple matching variations were found."))

            return matches[0]
        return value

    def assign(self, value, voucher: Voucher, **kwargs):
        voucher.quota = value


class SeatColumn(ImportColumn):
    identifier = 'seat'
    verbose_name = gettext_lazy('Seat ID')

    def __init__(self, *args):
        self._cached = set()
        super().__init__(*args)

    def clean(self, value, previous_values):
        if value:
            if self.event.has_subevents:
                if not previous_values.get('subevent'):
                    raise ValidationError(_('You need to choose a date if you select a seat.'))

            try:
                value = Seat.objects.get(
                    event=self.event,
                    seat_guid=value,
                    subevent=previous_values.get('subevent')
                )
            except Seat.MultipleObjectsReturned:
                raise ValidationError(_('Multiple matching seats were found.'))
            except Seat.DoesNotExist:
                raise ValidationError(_('No matching seat was found.'))
            if not value.is_available() or value in self._cached:
                raise ValidationError(
                    _('The seat you selected has already been taken. Please select a different seat.'))

            if previous_values.get("quota"):
                raise ValidationError(_('You need to choose a specific product if you select a seat.'))

            if previous_values.get('max_usages', 1) > 1 or previous_values.get('min_usages', 1) > 1:
                raise ValidationError(_('Seat-specific vouchers can only be used once.'))

            if previous_values.get("item") and value.product != previous_values.get("item"):
                raise ValidationError(
                    _('You need to choose the product "{prod}" for this seat.').format(prod=value.product)
                )

            self._cached.add(value)
        return value

    def assign(self, value, voucher: Voucher, **kwargs):
        voucher.seat = value


class TagColumn(ImportColumn):
    identifier = 'tag'
    verbose_name = gettext_lazy('Tag')

    def assign(self, value, voucher: Voucher, **kwargs):
        voucher.tag = value or ''


class CommentColumn(ImportColumn):
    identifier = 'comment'
    verbose_name = gettext_lazy('Comment')

    def assign(self, value, voucher: Voucher, **kwargs):
        voucher.comment = value or ''


class ShowHiddenItemsColumn(BooleanColumnMixin, ImportColumn):
    identifier = 'show_hidden_items'
    verbose_name = gettext_lazy('Shows hidden products that match this voucher')
    initial = "static:true"

    def assign(self, value, obj: Voucher, **kwargs):
        obj.show_hidden_items = value


class AllAddonsIncludedColumn(BooleanColumnMixin, ImportColumn):
    identifier = 'all_addons_included'
    verbose_name = gettext_lazy('Offer all add-on products for free when redeeming this voucher')

    def assign(self, value, obj: Voucher, **kwargs):
        obj.all_addons_included = value


class AllBundlesIncludedColumn(BooleanColumnMixin, ImportColumn):
    identifier = 'all_bundles_included'
    verbose_name = gettext_lazy('Include all bundled products without a designated price when redeeming this voucher')

    def assign(self, value, obj: Voucher, **kwargs):
        obj.all_bundles_included = value


def get_voucher_import_columns(event):
    default = []
    if event.has_subevents:
        default.append(SubeventColumn(event))
    default += [
        CodeColumn(event),
        MaxUsagesColumn(event),
        MinUsagesColumn(event),
        BudgetColumn(event),
        ValidUntilColumn(event),
        BlockQuotaColumn(event),
        AllowIgnoreQuotaColumn(event),
        PriceModeColumn(event),
        ValueColumn(event),
        ItemColumn(event),
        VariationColumn(event),
        QuotaColumn(event),
        SeatColumn(event),
        TagColumn(event),
        CommentColumn(event),
        ShowHiddenItemsColumn(event),
        AllAddonsIncludedColumn(event),
        AllBundlesIncludedColumn(event),
    ]

    for recv, resp in voucher_import_columns.send(sender=event):
        default += resp

    return default
