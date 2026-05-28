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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Sohalt, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import csv
from collections import Counter, namedtuple
from io import StringIO

from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import EmailValidator
from django.db.models import Count, F, Max
from django.db.models.functions import Upper
from django.forms.utils import ErrorDict
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelChoiceField

from pretix.base.email import get_available_placeholders
from pretix.base.forms import (
    I18nModelForm, MarkdownTextarea, PlaceholderValidator,
)
from pretix.base.forms.widgets import format_placeholders_help_text
from pretix.base.i18n import language
from pretix.base.models import Item, ItemVariation, Quota, SubEvent, Voucher
from pretix.base.services.locking import lock_objects
from pretix.base.services.quotas import QuotaAvailability
from pretix.control.forms import SplitDateTimeField, SplitDateTimePickerWidget
from pretix.control.forms.widgets import Select2, Select2ItemVarQuota
from pretix.control.signals import voucher_form_validation
from pretix.helpers.models import modelcopy


class FakeChoiceField(forms.ChoiceField):
    def valid_value(self, value):
        return True


class VoucherForm(I18nModelForm):
    itemvar = FakeChoiceField(
        label=_("Product"),
        help_text=_(
            "This product is added to the user's cart if the voucher is redeemed. Instead of a specific product, you "
            "can also select a quota. In this case, all products assigned to this quota can be selected."
        ),
        required=True
    )

    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'code', 'valid_until', 'block_quota', 'allow_ignore_quota', 'value', 'tag',
            'comment', 'max_usages', 'min_usages', 'price_mode', 'subevent', 'show_hidden_items', 'all_addons_included',
            'all_bundles_included', 'budget'
        ]
        field_classes = {
            'valid_until': SplitDateTimeField,
            'subevent': SafeModelChoiceField,
        }
        widgets = {
            'valid_until': SplitDateTimePickerWidget(),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        initial = kwargs.get('initial')
        self.initial_instance_data = None
        if instance:
            if instance.pk:
                self.initial_instance_data = modelcopy(instance)
            try:
                if instance.variation:
                    initial['itemvar'] = '%d-%d' % (instance.item.pk, instance.variation.pk)
                elif instance.item:
                    initial['itemvar'] = str(instance.item.pk)
                elif instance.quota:
                    initial['itemvar'] = 'q-%d' % instance.quota.pk
            except Item.DoesNotExist:
                pass
        super().__init__(*args, **kwargs)
        if not self.event and self.instance:
            self.event = self.instance.event

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
            self.fields['subevent'].required = False
        elif 'subevent':
            del self.fields['subevent']

        choices = []
        prefix = (self.prefix + '-') if self.prefix else ''
        if 'itemvar' in initial or (self.data and prefix + 'itemvar' in self.data):
            iv = self.data.get(prefix + 'itemvar', '') or initial.get('itemvar', '') or ''
            if iv.startswith('q-'):
                q = self.event.quotas.get(pk=iv[2:])
                choices.append(('q-%d' % q.pk, _('Any product in quota "{quota}"').format(quota=q)))
            elif '-' in iv:
                itemid, varid = iv.split('-')
                i = self.event.items.get(pk=itemid)
                v = i.variations.get(pk=varid)
                choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (str(i), v.value)))
            elif iv:
                i = self.event.items.get(pk=iv)
                if i.variations.exists():
                    choices.append((str(i.pk), _('{product} – Any variation').format(product=i)))
                else:
                    choices.append((str(i.pk), str(i)))

        self.fields['itemvar'].choices = choices
        self.fields['itemvar'].widget = Select2ItemVarQuota(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.vouchers.itemselect2', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('All products')
            }
        )
        self.fields['itemvar'].required = False
        self.fields['itemvar'].widget.choices = self.fields['itemvar'].choices

        if self.event.seating_plan or self.event.subevents.filter(seating_plan__isnull=False).exists():
            self.fields['seat'] = forms.CharField(
                label=_("Specific seat ID"),
                max_length=255,
                required=False,
                widget=forms.TextInput(attrs={'data-seat-guid-field': '1'}),
                initial=self.instance.seat.seat_guid if self.instance.seat else '',
                help_text=str(self.instance.seat) if self.instance.seat else '',
            )

    def parse_itemvar(self, data):
        try:
            itemid = quotaid = None
            iv = data.get('itemvar', '')
            if iv.startswith('q-'):
                quotaid = iv[2:]
            elif '-' in iv:
                itemid, varid = iv.split('-')
            elif iv:
                itemid, varid = iv, None
            else:
                itemid, varid = None, None

            if itemid:
                item = self.event.items.get(pk=itemid)
                if varid:
                    variation = item.variations.get(pk=varid)
                else:
                    variation = None
                quota = None
            elif quotaid:
                quota = self.event.quotas.get(pk=quotaid)
                item = None
                variation = None
            else:
                quota = None
                item = None
                variation = None

            return (item, variation, quota)

        except ObjectDoesNotExist:
            raise ValidationError(_("Invalid product selected."))

    def clean(self):
        data = super().clean()

        if not self._errors:
            self.instance.item, self.instance.variation, self.instance.quota = self.parse_itemvar(self.data)

        if 'codes' in data:
            data['codes'] = [a.strip() for a in data.get('codes', '').strip().split("\n") if a]
            cnt = len(data['codes']) * data.get('max_usages', 0)
        else:
            cnt = data.get('max_usages', 0)
            if self.instance and self.instance.pk:
                cnt -= self.instance.redeemed  # these do not need quota any more

        try:
            Voucher.clean_item_properties(
                data, self.event,
                self.instance.quota, self.instance.item, self.instance.variation,
                seats_given=data.get('seat') or data.get('seats'),
                block_quota=data.get('block_quota')
            )
        except ValidationError as e:
            raise ValidationError({"itemvar": e.message})
        if not data.get('show_hidden_items') and (
            (self.instance.quota and all(i.hide_without_voucher for i in self.instance.quota.items.all()))
            or (self.instance.item and self.instance.item.hide_without_voucher)
        ):
            raise ValidationError({
                'show_hidden_items': [
                    _('The voucher only matches hidden products but you have not selected that it should show '
                      'them.')
                ]
            })

        try:
            Voucher.clean_subevent(
                data, self.event
            )
        except ValidationError as e:
            raise ValidationError({"subevent": e.message})
        try:
            Voucher.clean_max_usages(data, self.instance.redeemed)
        except ValidationError as e:
            raise ValidationError({"max_usages": e})
        check_quota = Voucher.clean_quota_needs_checking(
            data, self.initial_instance_data,
            item_changed=data.get('itemvar') != self.initial.get('itemvar'),
            creating=not self.instance.pk
        )
        if check_quota:
            Voucher.clean_quota_check(
                data, cnt, self.initial_instance_data,
                self.event, self.instance.quota, self.instance.item, self.instance.variation
            )
        Voucher.clean_voucher_code(data, self.event, self.instance.pk)
        if 'seat' in self.fields:
            if data.get('seat'):
                self.instance.seat = Voucher.clean_seat_id(
                    data, self.instance.item, self.instance.quota, self.event, self.instance.pk
                )
                self.instance.item = self.instance.seat.product
            else:
                self.instance.seat = None

        voucher_form_validation.send(sender=self.event, form=self, data=data)

        return data

    def save(self, commit=True):
        return super().save(commit)


class VoucherBulkEditForm(VoucherForm):
    def __init__(self, *args, **kwargs):
        self.mixed_values = kwargs.pop('mixed_values')
        self.queryset = kwargs.pop('queryset')
        super().__init__(**kwargs)
        del self.fields["code"]
        self.fields.pop("seat", None)

    def is_bulk_checked(self, fieldname):
        return self.prefix + fieldname in self.data.getlist('_bulk')

    def clean(self):
        # We skip the parent class because it's not suited for bulk editing and implement custom validation here.
        # This does not validate *everything* we validate in VoucherForm. For example, we skip validation that one does
        # not create a voucher for an add-on product or that the seat matches the product to save on complexity.
        # This is a UX validation only anyway, since one could first create the voucher and then make the product an
        # add-on product. However, we need to validate everything that we don't want violated in the database.
        data = super(VoucherForm, self).clean()

        if self.is_bulk_checked("itemvar"):
            data["item"], data["variation"], data["quota"] = self.parse_itemvar(data)

        if self.is_bulk_checked("max_usages") and "max_usages" in data:
            max_redeemed = self.queryset.aggregate(m=Max("redeemed"))["m"]
            if data["max_usages"] < max_redeemed:
                raise ValidationError(_(
                    "You cannot reduce the maximum number of redemptions to %(max_usages)s, because at least one "
                    "of the selected vouchers has already been redeemed %(max_redeemed)s times."
                ) % {"max_usages": data["max_usages"], "max_redeemed": max_redeemed})

        # Check diff on product and quota usage based on old groups of vouchers
        if any(self.is_bulk_checked(k) for k in ("max_usages", "itemvar", "block_quota", "valid_until", "subevent")):
            quota_diff = Counter()

            current_vouchers = self.queryset.order_by().values(
                "item", "variation", "quota", "block_quota", "valid_until", "subevent", "redeemed", "max_usages",
                "allow_ignore_quota",
            ).annotate(c=Count("*"))
            item_cache = {i.pk: i for i in Item.objects.filter(pk__in=[c["item"] for c in current_vouchers])}
            var_cache = {v.pk: v for v in ItemVariation.objects.filter(pk__in=[c["variation"] for c in current_vouchers])}
            quota_cache = {q.pk: q for q in Quota.objects.filter(pk__in=[c["quota"] for c in current_vouchers])}
            subevent_cache = {s.pk: s for s in SubEvent.objects.filter(pk__in=[c["subevent"] for c in current_vouchers])}

            for current in current_vouchers:
                # Get quotas that are currently used
                if current["item"]:
                    current["item"] = item_cache[current["item"]]
                if current["variation"]:
                    current["variation"] = var_cache[current["variation"]]
                if current["quota"]:
                    current["quota"] = quota_cache[current["quota"]]
                if current["subevent"]:
                    current["subevent"] = subevent_cache[current["subevent"]]

                was_valid = current["valid_until"] is None or current["valid_until"] >= now()
                if was_valid and current["block_quota"] and current["max_usages"] > current["redeemed"]:
                    old_quotas = Voucher.get_affected_quotas(current["quota"], current["item"], current["variation"], current["subevent"])
                else:
                    old_quotas = set()
                old_amount = max(current["max_usages"] - current["redeemed"], 0) * current["c"]

                # Predict state after change
                after_change = dict(current)
                if self.is_bulk_checked("itemvar") and "itemvar" in data:
                    after_change["item"] = data["item"]
                    after_change["variation"] = data["variation"]
                    after_change["quota"] = data["quota"]
                if self.is_bulk_checked("subevent") and "subevent" in data:
                    after_change["subevent"] = data["subevent"]
                if self.is_bulk_checked("max_usages") and "max_usages" in data:
                    after_change["max_usages"] = data["max_usages"]
                if self.is_bulk_checked("block_quota") and "block_quota" in data:
                    after_change["block_quota"] = data["block_quota"]
                if self.is_bulk_checked("valid_until") and "valid_until" in data:
                    after_change["valid_until"] = data["valid_until"]
                if self.is_bulk_checked("allow_ignore_quota") and "allow_ignore_quota" in data:
                    after_change["allow_ignore_quota"] = data["allow_ignore_quota"]

                if after_change["quota"] and self.event.has_subevents and not after_change["subevent"]:
                    raise ValidationError(_("You cannot create a voucher that allows selection of a quota but has no date selected."))

                if after_change["quota"] and after_change["subevent"] and after_change["quota"].subevent_id != after_change["subevent"].pk:
                    raise ValidationError(_("The selected quota does not match the selected subevent."))

                if after_change["block_quota"] and self.event.has_subevents and not after_change["subevent"]:
                    raise ValidationError(
                        _('If you want this voucher to block quota, you need to select a specific date.'))

                if after_change["block_quota"] and not after_change["item"] and not after_change["quota"]:
                    raise ValidationError(
                        _('You need to select a specific product or quota if this voucher should reserve '
                          'tickets.')
                    )

                if after_change["allow_ignore_quota"]:
                    # todo: is this the most useful way to do this?
                    continue

                will_be_valid = after_change["valid_until"] is None or after_change["valid_until"] >= now()
                if will_be_valid and after_change["block_quota"] and after_change["max_usages"] > current["redeemed"]:
                    new_quotas = Voucher.get_affected_quotas(after_change["quota"], after_change["item"], after_change["variation"], after_change["subevent"])
                else:
                    new_quotas = set()

                new_amount = max(after_change["max_usages"] - after_change["redeemed"], 0) * current["c"]
                if new_quotas != old_quotas or new_amount != old_amount:
                    for q in old_quotas:
                        quota_diff[q] -= old_amount
                    for q in new_quotas:
                        quota_diff[q] += new_amount

            if any(v > 0 for q, v in quota_diff.items()):
                lock_objects([q for q, v in quota_diff.items() if q.size is not None and v > 0], shared_lock_objects=[self.event])
                qa = QuotaAvailability(count_waitinglist=False)
                qa.queue(*(q for q, v in quota_diff.items() if v > 0))
                qa.compute()

                if any(qa.results[q][0] != Quota.AVAILABILITY_OK or (qa.results[q][1] is not None and qa.results[q][1] < required)
                       for q, required in quota_diff.items() if required > 0):
                    raise ValidationError(_(
                        'There is no sufficient quota available to perform this change.'
                    ))

        has_seat = self.queryset.filter(seat__isnull=False).exists()
        if has_seat:
            if self.is_bulk_checked("max_usages"):
                raise ValidationError(_(
                    'Changing the maximum number of usages in bulk is not supported if any of the selected vouchers '
                    'is assigned a seat.'
                ))
            if self.is_bulk_checked("subevent"):
                raise ValidationError(pgettext_lazy(
                    'subevent',
                    'Changing the date in bulk is not supported if any of the selected vouchers '
                    'is assigned a seat.'
                ))
            if self.is_bulk_checked("itemvar") and data["quota"]:
                raise ValidationError(_(
                    'Changing the product to a quota is not supported if any of the selected vouchers '
                    'is assigned a seat.'
                ))

            if self.is_bulk_checked("valid_until"):
                if data["valid_until"] is None or data["valid_until"] >= now():
                    currently_not_blocked_seats = self.queryset.filter(
                        seat__isnull=False,
                        max_usages__gt=F("redeemed"),
                        valid_until__lt=now(),
                    )
                    if self.event.has_subevents:
                        subevents = self.event.subevents.filter(pk__in=currently_not_blocked_seats.values_list("subevent"))
                        for se in subevents:
                            conflicts = currently_not_blocked_seats.filter(
                                subevent=se
                            ).exclude(
                                seat_id__in=se.free_seats().values("pk")
                            )
                            if conflicts:
                                raise ValidationError(_(
                                    'This change cannot be completed because not all assigned seats of the vouchers are '
                                    'still available'
                                ))
                    else:
                        conflicts = currently_not_blocked_seats.exclude(
                            seat_id__in=self.event.free_seats().values("pk")
                        )
                        if conflicts:
                            raise ValidationError(_(
                                'This change cannot be completed because not all assigned seats of the vouchers are '
                                'still available'
                            ))

        return data

    def save(self, commit=True):
        objs = list(self.queryset)
        fields = set()

        check_map = {
            'price_mode': '__price',
            'value': '__price',
        }
        for k in self.fields:
            if not self.is_bulk_checked(check_map.get(k, k)):
                continue

            if k == 'itemvar':
                fields.add("item")
                fields.add("variation")
                fields.add("quota")
            else:
                fields.add(k)
            for obj in objs:
                if k == 'itemvar':
                    obj.item = self.cleaned_data["item"]
                    obj.variation = self.cleaned_data["variation"]
                    obj.quota = self.cleaned_data["quota"]
                else:
                    setattr(obj, k, self.cleaned_data[k])

        fields = [f for f in fields if f != 'itemvars']
        if fields:
            Voucher.objects.bulk_update(objs, fields, 200)

    def full_clean(self):
        if len(self.data) == 0:
            # form wasn't submitted
            self._errors = ErrorDict()
            return
        super().full_clean()

    def _post_clean(self):
        pass  # skip model-level clean


class VoucherBulkForm(VoucherForm):
    codes = forms.CharField(
        widget=forms.Textarea,
        label=_("Codes"),
        help_text=_(
            "Add one voucher code per line. We suggest that you copy this list and save it into a file."
        ),
        required=True
    )
    send = forms.BooleanField(
        label=_("Send vouchers via email"),
        required=False
    )
    send_subject = forms.CharField(
        label=_("Subject"),
        widget=forms.TextInput(attrs={'data-display-dependency': '#id_send'}),
        required=False,
        initial=_('Your voucher for {event}')
    )
    send_message = forms.CharField(
        label=_("Message"),
        widget=MarkdownTextarea(attrs={'data-display-dependency': '#id_send'}),
        required=False,
        initial=_('Hello,\n\n'
                  'with this email, we\'re sending you one or more vouchers for {event}:\n\n{voucher_list}\n\n'
                  'You can redeem them here in our ticket shop:\n\n{url}\n\nBest regards,  \n'
                  'Your {event} team')
    )
    send_recipients = forms.CharField(
        label=_('Recipients'),
        widget=forms.Textarea(attrs={
            'data-display-dependency': '#id_send',
            'placeholder': 'email,number,name,tag\njohn@example.org,3,John,example\n\n-- {} --\n\njohn@example.org\njane@example.net'.format(
                _('or')
            )
        }),
        required=False,
        help_text=_('You can either supply a list of email addresses with one email address per line, or the contents '
                    'of a CSV file with a title row and one or more of the columns "email", "number", "name", '
                    'or "tag".')
    )
    Recipient = namedtuple('Recipient', 'email number name tag')

    def _set_field_placeholders(self, fn, base_parameters, rich=False):
        placeholders = get_available_placeholders(self.instance.event, base_parameters, rich=rich)
        ht = format_placeholders_help_text(placeholders, self.instance.event)

        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(['{%s}' % p for p in placeholders.keys()])
        )

    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'valid_until', 'block_quota', 'allow_ignore_quota', 'value', 'tag', 'comment',
            'max_usages', 'min_usages', 'price_mode', 'subevent', 'show_hidden_items', 'all_addons_included',
            'all_bundles_included', 'budget'
        ]
        field_classes = {
            'valid_until': SplitDateTimeField,
            'subevent': SafeModelChoiceField,
        }
        widgets = {
            'valid_until': SplitDateTimePickerWidget(),
        }
        labels = {
            'max_usages': _('Maximum usages per voucher')
        }
        help_texts = {
            'max_usages': _('Number of times times EACH of these vouchers can be redeemed.')
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_field_placeholders('send_subject', ['event', 'name'])
        self._set_field_placeholders('send_message', ['event', 'voucher_list', 'name'], rich=True)

        with language(self.instance.event.settings.locale, self.instance.event.settings.region):
            for f in ("send_subject", "send_message"):
                self.fields[f].initial = str(self.fields[f].initial)

        if 'seat' in self.fields:
            self.fields['seats'] = forms.CharField(
                label=_("Specific seat IDs"),
                required=False,
                widget=forms.Textarea(attrs={'data-seat-guid-field': '1'}),
                initial=self.instance.seat.seat_guid if self.instance.seat else '',
            )

    def clean_send_recipients(self):
        raw = self.cleaned_data['send_recipients']
        if self.cleaned_data.get('send', None) is False:
            # No need to validate addresses if the section was turned off
            return []
        if not raw:
            return []
        r = raw.split('\n')
        res = []
        if ',' in raw or ';' in raw:
            if '@' in r[0]:
                raise ValidationError(_('CSV input needs to contain a header row in the first line.'))
            try:
                dialect = csv.Sniffer().sniff(raw[:1024])
                reader = csv.DictReader(StringIO(raw), dialect=dialect)
            except csv.Error as e:
                raise ValidationError(_('CSV parsing failed: {error}.').format(error=str(e)))
            if len(reader.fieldnames) == 1 and ',' in reader.fieldnames[0]:
                raise ValidationError(_('CSV input was not recognized to have multiple columns, maybe you have some invalid quoted field in your input.'))
            if 'email' not in reader.fieldnames:
                raise ValidationError(_('CSV input needs to contain a field with the header "{header}".').format(header="email"))
            unknown_fields = [f for f in reader.fieldnames if f not in ('email', 'name', 'tag', 'number')]
            if unknown_fields:
                raise ValidationError(_('CSV input contains an unknown field with the header "{header}".').format(header=unknown_fields[0]))
            for i, row in enumerate(reader):
                try:
                    EmailValidator()(row['email'].strip())
                except ValidationError as err:
                    raise ValidationError(_('{value} is not a valid email address.').format(value=row['email'].strip())) from err
                try:
                    res.append(self.Recipient(
                        name=row.get('name', ''),
                        email=row['email'].strip(),
                        number=int(row.get('number', 1) or ""),
                        tag=row.get('tag', None)
                    ))
                except ValueError as err:
                    raise ValidationError(_('Invalid value in row {number}.').format(number=i + 1)) from err
        else:
            for e in r:
                try:
                    EmailValidator()(e.strip())
                except ValidationError as err:
                    raise ValidationError(_('{value} is not a valid email address.').format(value=e.strip())) from err
                else:
                    res.append(self.Recipient(email=e.strip(), number=1, tag=None, name=''))
        return res

    def clean(self):
        data = super().clean()

        if 'codes' in data:
            vouchers = self.instance.event.vouchers.annotate(
                code_upper=Upper('code')
            ).filter(code_upper__in=[c.upper() for c in data['codes']])
            if vouchers.exists():
                raise ValidationError(_('A voucher with one of these codes already exists.'))

            codes_seen = set()
            for c in data['codes']:
                if len(c) < 5:
                    raise ValidationError({
                        'codes': [
                            _('The voucher code {code} is too short. Make sure all voucher codes are at least {min_length} characters long.').format(
                                code=c,
                                min_length=5
                            )
                        ]
                    })
                if c in codes_seen:
                    raise ValidationError(_('The voucher code {code} appears in your list twice.').format(code=c))
                codes_seen.add(c)

        if data.get('send') and not all([data.get('send_subject'), data.get('send_message'), data.get('send_recipients')]):
            raise ValidationError(_('If vouchers should be sent by email, subject, message and recipients need to be specified.'))

        if data.get('codes') and data.get('send'):
            recp = self.cleaned_data.get('send_recipients', [])
            code_len = len(data.get('codes'))
            recp_len = sum(r.number for r in recp)
            if code_len != recp_len:
                raise ValidationError(_('You generated {codes} vouchers, but entered recipients for {recp} vouchers.').format(codes=code_len, recp=recp_len))

        if data.get('seats'):
            seatids = [s.strip() for s in data.get('seats').strip().split("\n") if s]
            if len(seatids) != len(data.get('codes')):
                raise ValidationError(_('You need to specify as many seats as voucher codes.'))
            data['seats'] = []
            for s in seatids:
                data['seat'] = s
                data['seats'].append(Voucher.clean_seat_id(
                    data, self.instance.item, self.instance.quota, self.instance.event, None
                ))
            self.instance.seat = data['seats'][0]  # Trick model-level validation
        else:
            data['seats'] = []

        return data

    def post_bulk_save(self, objs):
        pass
