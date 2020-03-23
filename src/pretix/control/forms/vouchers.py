import csv
from collections import namedtuple
from io import StringIO

from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import EmailValidator
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelChoiceField

from pretix.base.email import get_available_placeholders
from pretix.base.forms import I18nModelForm, PlaceholderValidator
from pretix.base.models import Item, Voucher
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
            "This product is added to the user's cart if the voucher is redeemed."
        ),
        required=True
    )

    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'code', 'valid_until', 'block_quota', 'allow_ignore_quota', 'value', 'tag',
            'comment', 'max_usages', 'price_mode', 'subevent', 'show_hidden_items', 'budget'
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
        if instance:
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
        else:
            self.initial_instance_data = None
        super().__init__(*args, **kwargs)

        if instance.event.has_subevents:
            self.fields['subevent'].queryset = instance.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': instance.event.slug,
                        'organizer': instance.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'Date')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
            self.fields['subevent'].required = False
        elif 'subevent':
            del self.fields['subevent']

        choices = []
        if 'itemvar' in initial or (self.data and 'itemvar' in self.data):
            iv = self.data.get('itemvar') or initial.get('itemvar', '')
            if iv.startswith('q-'):
                q = self.instance.event.quotas.get(pk=iv[2:])
                choices.append(('q-%d' % q.pk, _('Any product in quota "{quota}"').format(quota=q)))
            elif '-' in iv:
                itemid, varid = iv.split('-')
                i = self.instance.event.items.get(pk=itemid)
                v = i.variations.get(pk=varid)
                choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (str(i), v.value)))
            elif iv:
                i = self.instance.event.items.get(pk=iv)
                if i.variations.exists():
                    choices.append((str(i.pk), _('{product} – Any variation').format(product=i)))
                else:
                    choices.append((str(i.pk), str(i)))

        self.fields['itemvar'].choices = choices
        self.fields['itemvar'].widget = Select2ItemVarQuota(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.vouchers.itemselect2', kwargs={
                    'event': instance.event.slug,
                    'organizer': instance.event.organizer.slug,
                }),
                'data-placeholder': _('All products')
            }
        )
        self.fields['itemvar'].required = False
        self.fields['itemvar'].widget.choices = self.fields['itemvar'].choices

        if self.instance.event.seating_plan or self.instance.event.subevents.filter(seating_plan__isnull=False).exists():
            self.fields['seat'] = forms.CharField(
                label=_("Specific seat ID"),
                max_length=255,
                required=False,
                widget=forms.TextInput(attrs={'data-seat-guid-field': '1'}),
                initial=self.instance.seat.seat_guid if self.instance.seat else '',
                help_text=str(self.instance.seat) if self.instance.seat else '',
            )

    def clean(self):
        data = super().clean()

        if not self._errors and self.data.get('itemvar'):
            try:
                itemid = quotaid = None
                iv = self.data.get('itemvar', '')
                if iv.startswith('q-'):
                    quotaid = iv[2:]
                elif '-' in iv:
                    itemid, varid = iv.split('-')
                else:
                    itemid, varid = iv, None

                if itemid:
                    self.instance.item = self.instance.event.items.get(pk=itemid)
                    if varid:
                        self.instance.variation = self.instance.item.variations.get(pk=varid)
                    else:
                        self.instance.variation = None
                    self.instance.quota = None

                else:
                    self.instance.quota = self.instance.event.quotas.get(pk=quotaid)
                    self.instance.item = None
                    self.instance.variation = None
            except ObjectDoesNotExist:
                raise ValidationError(_("Invalid product selected."))

        if 'codes' in data:
            data['codes'] = [a.strip() for a in data.get('codes', '').strip().split("\n") if a]
            cnt = len(data['codes']) * data.get('max_usages', 0)
        else:
            cnt = data.get('max_usages', 0)

        Voucher.clean_item_properties(
            data, self.instance.event,
            self.instance.quota, self.instance.item, self.instance.variation,
            seats_given=data.get('seat') or data.get('seats'),
            block_quota=data.get('block_quota')
        )
        if not self.instance.show_hidden_items and (
            (self.instance.quota and all(i.hide_without_voucher for i in self.instance.quota.items.all()))
            or (self.instance.item and self.instance.item.hide_without_voucher)
        ):
            raise ValidationError({
                'show_hidden_items': [
                    _('The voucher only matches hidden products but you have not selected that it should show '
                      'them.')
                ]
            })
        Voucher.clean_subevent(
            data, self.instance.event
        )
        Voucher.clean_max_usages(data, self.instance.redeemed)
        check_quota = Voucher.clean_quota_needs_checking(
            data, self.initial_instance_data,
            item_changed=data.get('itemvar') != self.initial.get('itemvar'),
            creating=not self.instance.pk
        )
        if check_quota:
            Voucher.clean_quota_check(
                data, cnt, self.initial_instance_data, self.instance.event,
                self.instance.quota, self.instance.item, self.instance.variation
            )
        Voucher.clean_voucher_code(data, self.instance.event, self.instance.pk)
        if 'seat' in self.fields and data.get('seat'):
            self.instance.seat = Voucher.clean_seat_id(
                data, self.instance.item, self.instance.quota, self.instance.event, self.instance.pk
            )
            self.instance.item = self.instance.seat.product

        voucher_form_validation.send(sender=self.instance.event, form=self, data=data)

        return data

    def save(self, commit=True):
        return super().save(commit)


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
        widget=forms.Textarea(attrs={'data-display-dependency': '#id_send'}),
        required=False,
        initial=_('Hello,\n\n'
                  'with this email, we\'re sending you one or more vouchers for {event}:\n\n{voucher_list}\n\n'
                  'You can redeem them here in our ticket shop:\n\n{url}\n\nBest regards,\n\n'
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
        help_text=_('You can either supply a list of email addresses with one email address per line, or a CSV file with a title column '
                    'and one or more of the columns "email", "number", "name", or "tag".')
    )
    Recipient = namedtuple('Recipient', 'email number name tag')

    def _set_field_placeholders(self, fn, base_parameters):
        phs = [
            '{%s}' % p
            for p in sorted(get_available_placeholders(self.instance.event, base_parameters).keys())
        ]
        ht = _('Available placeholders: {list}').format(
            list=', '.join(phs)
        )
        if self.fields[fn].help_text:
            self.fields[fn].help_text += ' ' + str(ht)
        else:
            self.fields[fn].help_text = ht
        self.fields[fn].validators.append(
            PlaceholderValidator(phs)
        )

    class Meta:
        model = Voucher
        localized_fields = '__all__'
        fields = [
            'valid_until', 'block_quota', 'allow_ignore_quota', 'value', 'tag', 'comment',
            'max_usages', 'price_mode', 'subevent', 'show_hidden_items', 'budget'
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
        self._set_field_placeholders('send_message', ['event', 'voucher_list', 'name'])
        if 'seat' in self.fields:
            self.fields['seats'] = forms.CharField(
                label=_("Specific seat IDs"),
                required=False,
                widget=forms.Textarea(attrs={'data-seat-guid-field': '1'}),
                initial=self.instance.seat.seat_guid if self.instance.seat else '',
            )

    def clean_send_recipients(self):
        raw = self.cleaned_data['send_recipients']
        if not raw:
            return []
        r = raw.split('\n')
        res = []
        if ',' in raw or ';' in raw:
            if '@' in r[0]:
                raise ValidationError(_('CSV input needs to contain a header row in the first line.'))
            dialect = csv.Sniffer().sniff(raw[:1024])
            reader = csv.DictReader(StringIO(raw), dialect=dialect)
            if 'email' not in reader.fieldnames:
                raise ValidationError(_('CSV input needs to contain a field with the header "{header}".').format(header="email"))
            unknown_fields = [f for f in reader.fieldnames if f not in ('email', 'name', 'tag', 'number')]
            if unknown_fields:
                raise ValidationError(_('CSV input contains an unknown field with the header "{header}".').format(header=unknown_fields[0]))
            for i, row in enumerate(reader):
                try:
                    EmailValidator()(row['email'])
                except ValidationError as err:
                    raise ValidationError(_('{value} is not a valid email address.').format(value=row['email'])) from err
                try:
                    res.append(self.Recipient(
                        name=row.get('name', ''),
                        email=row['email'].strip(),
                        number=int(row.get('number', 1)),
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

        vouchers = self.instance.event.vouchers.annotate(
            code_lower=Lower('code')
        ).filter(code_lower__in=[c.lower() for c in data['codes']])
        if vouchers.exists():
            raise ValidationError(_('A voucher with one of these codes already exists.'))

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

    def save(self, event, *args, **kwargs):
        objs = []
        for code in self.cleaned_data['codes']:
            obj = modelcopy(self.instance)
            obj.event = event
            obj.code = code
            try:
                obj.seat = self.cleaned_data['seats'].pop()
                obj.item = obj.seat.product
            except IndexError:
                pass
            data = dict(self.cleaned_data)
            data['code'] = code
            data['bulk'] = True
            del data['codes']
            objs.append(obj)
        Voucher.objects.bulk_create(objs)
        objs = []
        for v in event.vouchers.filter(code__in=self.cleaned_data['codes']):
            # We need to query them again as bulk_create does not fill in .pk values on databases
            # other than PostgreSQL
            objs.append(v)
        return objs
