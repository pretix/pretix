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
# This file contains Apache-licensed contributions copyrighted by: Jakob Schnell, Tobias Kunze
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

from datetime import datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django import forms
from django.apps import apps
from django.conf import settings
from django.db.models import (
    Count, Exists, F, Max, Model, OrderBy, OuterRef, Q, QuerySet,
)
from django.db.models.functions import Coalesce, ExtractWeekDay, Upper
from django.urls import reverse, reverse_lazy
from django.utils.formats import date_format, localize
from django.utils.functional import cached_property
from django.utils.timezone import get_current_timezone, make_aware, now
from django.utils.translation import gettext, gettext_lazy as _, pgettext_lazy
from django_scopes.forms import SafeModelChoiceField

from pretix.base.channels import get_all_sales_channels
from pretix.base.forms.widgets import (
    DatePickerWidget, SplitDateTimePickerWidget, TimePickerWidget,
)
from pretix.base.models import (
    Checkin, CheckinList, Device, Event, EventMetaProperty, EventMetaValue,
    Gate, Invoice, InvoiceAddress, Item, Order, OrderPayment, OrderPosition,
    OrderRefund, Organizer, Question, QuestionAnswer, SubEvent,
    SubEventMetaValue, Team, TeamAPIToken, TeamInvite, Voucher,
)
from pretix.base.signals import register_payment_providers
from pretix.control.forms.widgets import Select2, Select2ItemVarQuota
from pretix.control.signals import order_search_filter_q
from pretix.helpers.countries import CachedCountries
from pretix.helpers.database import (
    get_deterministic_ordering, rolledback_transaction,
)
from pretix.helpers.dicts import move_to_end
from pretix.helpers.i18n import i18ncomp

PAYMENT_PROVIDERS = []


def get_all_payment_providers():
    global PAYMENT_PROVIDERS

    if PAYMENT_PROVIDERS:
        return PAYMENT_PROVIDERS

    class FakeSettings:
        def __init__(self, orig_settings):
            self.orig_settings = orig_settings

        def set(self, *args, **kwargs):
            pass

        def __getattr__(self, item):
            return getattr(self.orig_settings, item)

    class FakeEvent:
        def __init__(self, orig_event):
            self.orig_event = orig_event

        @property
        def settings(self):
            return FakeSettings(self.orig_event.settings)

        def __getattr__(self, item):
            return getattr(self.orig_event, item)

        @property
        def __class__(self):  # hackhack
            return Event

    with rolledback_transaction():
        event = Event.objects.create(
            plugins=",".join([app.name for app in apps.get_app_configs()]),
            name="INTERNAL",
            date_from=now(),
            organizer=Organizer.objects.create(name="INTERNAL")
        )
        event = FakeEvent(event)
        provs = register_payment_providers.send(
            sender=event
        )
        choices = []
        for recv, prov in provs:
            if isinstance(prov, list):
                for p in prov:
                    p = p(event)
                    if not p.is_meta:
                        choices.append((p.identifier, p.verbose_name))
            else:
                prov = prov(event)
                if not prov.is_meta:
                    choices.append((prov.identifier, prov.verbose_name))
    PAYMENT_PROVIDERS = choices
    return choices


class FilterForm(forms.Form):
    orders = {}

    def filter_qs(self, qs):
        return qs

    @property
    def filtered(self):
        return self.is_valid() and any(self.cleaned_data.values())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ordering'] = forms.ChoiceField(
            choices=sum([
                [(a, a), ('-' + a, '-' + a)]
                for a in self.orders.keys()
            ], []),
            required=False
        )

    def get_order_by(self):
        o = self.cleaned_data.get('ordering')
        if o.startswith('-') and o not in self.orders:
            return '-' + self.orders[o[1:]]
        else:
            return self.orders[o]

    def filter_to_strings(self):
        string = []
        for k, f in self.fields.items():
            v = self.cleaned_data.get(k)
            if v is None or (isinstance(v, (list, str, QuerySet)) and len(v) == 0):
                continue
            if k == "saveas":
                continue

            if isinstance(v, bool):
                val = _('Yes') if v else _('No')
            elif isinstance(v, QuerySet):
                q = ['"' + str(m) + '"' for m in v]
                if not q:
                    continue
                val = ' or '.join(q)
            elif isinstance(v, Model):
                val = '"' + str(v) + '"'
            elif isinstance(f, forms.MultipleChoiceField):
                valdict = dict(f.choices)
                val = ' or '.join([str(valdict.get(m)) for m in v])
            elif isinstance(f, forms.ChoiceField):
                val = str(dict(f.choices).get(v))
            elif isinstance(v, datetime):
                val = date_format(v, 'SHORT_DATETIME_FORMAT')
            elif isinstance(v, Decimal):
                val = localize(v)
            else:
                val = v
            string.append('{}: {}'.format(f.label, val))
        return string


class OrderFilterForm(FilterForm):
    query = forms.CharField(
        label=_('Search for…'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search for…'),
            'autofocus': 'autofocus'
        }),
        required=False
    )
    provider = forms.ChoiceField(
        label=_('Payment provider'),
        choices=[
            ('', _('All payment providers')),
        ],
        required=False,
    )
    status = forms.ChoiceField(
        label=_('Order status'),
        choices=(
            ('', _('All orders')),
            (_('Valid orders'), (
                (Order.STATUS_PAID, _('Paid (or canceled with paid fee)')),
                (Order.STATUS_PAID + 'v', _('Paid or confirmed')),
                (Order.STATUS_PENDING, _('Pending')),
                (Order.STATUS_PENDING + Order.STATUS_PAID, _('Pending or paid')),
            )),
            (_('Cancellations'), (
                (Order.STATUS_CANCELED, _('Canceled (fully)')),
                ('cp', _('Canceled (fully or with paid fee)')),
                ('rc', _('Cancellation requested')),
                ('cni', _('Fully canceled but invoice not canceled')),
            )),
            (_('Payment process'), (
                (Order.STATUS_EXPIRED, _('Expired')),
                (Order.STATUS_PENDING + Order.STATUS_EXPIRED, _('Pending or expired')),
                ('o', _('Pending (overdue)')),
                ('overpaid', _('Overpaid')),
                ('partially_paid', _('Partially paid')),
                ('underpaid', _('Underpaid (but confirmed)')),
                ('pendingpaid', _('Pending (but fully paid)')),
            )),
            (_('Approval process'), (
                ('na', _('Approved, payment pending')),
                ('pa', _('Approval pending')),
            )),
            (_('Follow-up date'), (
                ('custom_followup_at', _('Follow-up configured')),
                ('custom_followup_due', _('Follow-up due')),
            )),
            ('testmode', _('Test mode')),
        ),
        required=False,
    )

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            u = fdata.get('query')

            if "-" in u:
                code = (Q(event__slug__icontains=u.rsplit("-", 1)[0])
                        & Q(code__icontains=Order.normalize_code(u.rsplit("-", 1)[1])))
            else:
                code = Q(code__icontains=Order.normalize_code(u))

            invoice_nos = {u, u.upper()}
            if u.isdigit():
                for i in range(2, 12):
                    invoice_nos.add(u.zfill(i))

            matching_invoices = Invoice.objects.filter(
                Q(invoice_no__in=invoice_nos)
                | Q(full_invoice_no__iexact=u)
            ).values_list('order_id', flat=True)
            matching_positions = OrderPosition.objects.filter(
                Q(
                    Q(attendee_name_cached__icontains=u) | Q(attendee_email__icontains=u)
                    | Q(secret__istartswith=u)
                    | Q(pseudonymization_id__istartswith=u)
                )
            ).values_list('order_id', flat=True)
            matching_invoice_addresses = InvoiceAddress.objects.filter(
                Q(
                    Q(name_cached__icontains=u) | Q(company__icontains=u)
                )
            ).values_list('order_id', flat=True)
            matching_orders = Order.objects.filter(
                code
                | Q(email__icontains=u)
                | Q(comment__icontains=u)
            ).values_list('id', flat=True)

            mainq = (
                Q(pk__in=matching_orders)
                | Q(pk__in=matching_invoices)
                | Q(pk__in=matching_positions)
                | Q(pk__in=matching_invoice_addresses)
            )
            for recv, q in order_search_filter_q.send(sender=getattr(self, 'event', None), query=u):
                mainq = mainq | q
            qs = qs.filter(
                mainq
            )

        if fdata.get('status'):
            s = fdata.get('status')
            if s == 'o':
                qs = qs.filter(status=Order.STATUS_PENDING, expires__lt=now().replace(hour=0, minute=0, second=0))
            elif s == 'np':
                qs = qs.filter(status__in=[Order.STATUS_PENDING, Order.STATUS_PAID])
            elif s == 'ne':
                qs = qs.filter(status__in=[Order.STATUS_PENDING, Order.STATUS_EXPIRED])
            elif s == 'pv':
                qs = qs.filter(Q(status=Order.STATUS_PAID) | Q(status=Order.STATUS_PENDING, valid_if_pending=True))
            elif s in ('p', 'n', 'e', 'c', 'r'):
                qs = qs.filter(status=s)
            elif s == 'overpaid':
                qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
                qs = qs.filter(
                    Q(~Q(status=Order.STATUS_CANCELED) & Q(pending_sum_t__lt=0))
                    | Q(Q(status=Order.STATUS_CANCELED) & Q(pending_sum_rc__lt=0))
                )
            elif s == 'rc':
                qs = qs.filter(
                    cancellation_requests__isnull=False
                ).annotate(
                    cancellation_request_time=Max('cancellation_requests__created')
                ).order_by(
                    '-cancellation_request_time'
                )
            elif s == 'pendingpaid':
                qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
                qs = qs.filter(
                    Q(status__in=(Order.STATUS_EXPIRED, Order.STATUS_PENDING)) & Q(pending_sum_t__lte=0)
                    & Q(require_approval=False)
                )
            elif s == 'partially_paid':
                qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
                qs = qs.filter(
                    computed_payment_refund_sum__lt=F('total'),
                    computed_payment_refund_sum__gt=Decimal('0.00')
                ).exclude(
                    status=Order.STATUS_CANCELED
                )
            elif s == 'underpaid':
                qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
                qs = qs.filter(
                    Q(status=Order.STATUS_PAID, pending_sum_t__gt=0) |
                    Q(status=Order.STATUS_CANCELED, pending_sum_rc__gt=0)
                )
            elif s == 'cni':
                i = Invoice.objects.filter(
                    order=OuterRef('pk'),
                    is_cancellation=False,
                    refered__isnull=True,
                ).order_by().values('order').annotate(k=Count('id')).values('k')
                qs = qs.annotate(
                    icnt=i
                ).filter(
                    icnt__gt=0,
                    status=Order.STATUS_CANCELED,
                )
            elif s == 'pa':
                qs = qs.filter(
                    status=Order.STATUS_PENDING,
                    require_approval=True
                )
            elif s == 'na':
                qs = qs.filter(
                    status=Order.STATUS_PENDING,
                    require_approval=False
                )
            elif s == 'custom_followup_at':
                qs = qs.filter(
                    custom_followup_at__isnull=False
                )
            elif s == 'custom_followup_due':
                qs = qs.filter(
                    custom_followup_at__lte=now().astimezone(get_current_timezone()).date()
                )
            elif s == 'testmode':
                qs = qs.filter(
                    testmode=True
                )
            elif s == 'cp':
                s = OrderPosition.objects.filter(
                    order=OuterRef('pk')
                )
                qs = qs.annotate(
                    has_pc=Exists(s)
                ).filter(
                    Q(status=Order.STATUS_PAID, has_pc=False) | Q(status=Order.STATUS_CANCELED)
                )

        if fdata.get('ordering'):
            qs = qs.order_by(*get_deterministic_ordering(Order, self.get_order_by()))

        if fdata.get('provider'):
            qs = qs.annotate(
                has_payment_with_provider=Exists(
                    OrderPayment.objects.filter(
                        Q(order=OuterRef('pk')) & Q(provider=fdata.get('provider'))
                    )
                )
            )
            qs = qs.filter(has_payment_with_provider=1)

        return qs


class EventOrderFilterForm(OrderFilterForm):
    orders = {'code': 'code', 'email': 'email', 'total': 'total',
              'datetime': 'datetime', 'status': 'status'}

    item = forms.ChoiceField(
        label=_('Products'),
        required=False,
    )
    subevent = forms.ModelChoiceField(
        label=pgettext_lazy('subevent', 'Date'),
        queryset=SubEvent.objects.none(),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )
    question = forms.ModelChoiceField(
        queryset=Question.objects.none(),
        required=False,
    )
    answer = forms.CharField(
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = self.event.items.all()
        self.fields['question'].queryset = self.event.questions.all()
        self.fields['provider'].choices += [(k, v.verbose_name) for k, v
                                            in self.event.get_payment_providers().items()]

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        elif 'subevent':
            del self.fields['subevent']

        choices = [('', _('All products'))]
        for i in self.event.items.prefetch_related('variations').all():
            variations = list(i.variations.all())
            if variations:
                choices.append((str(i.pk), _('{product} – Any variation').format(product=str(i))))
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (str(i), v.value)))
            else:
                choices.append((str(i.pk), str(i)))
        self.fields['item'].choices = choices

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        item = fdata.get('item')
        if item:
            if '-' in item:
                var = item.split('-')[1]
                qs = qs.filter(all_positions__variation_id=var, all_positions__canceled=False).distinct()
            else:
                qs = qs.filter(all_positions__item_id=fdata.get('item'), all_positions__canceled=False).distinct()

        if fdata.get('subevent'):
            qs = qs.filter(all_positions__subevent=fdata.get('subevent'), all_positions__canceled=False).distinct()

        if fdata.get('question') and fdata.get('answer') is not None:
            q = fdata.get('question')

            if q.type == Question.TYPE_FILE:
                answers = QuestionAnswer.objects.filter(
                    orderposition__order_id=OuterRef('pk'),
                    question_id=q.pk,
                    file__isnull=False
                )
                qs = qs.annotate(has_answer=Exists(answers)).filter(has_answer=True)
            elif q.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE) and fdata.get('answer'):
                answers = QuestionAnswer.objects.filter(
                    question_id=q.pk,
                    orderposition__order_id=OuterRef('pk'),
                    options__pk=fdata.get('answer')
                )
                qs = qs.annotate(has_answer=Exists(answers)).filter(has_answer=True)
            else:
                answers = QuestionAnswer.objects.filter(
                    question_id=q.pk,
                    orderposition__order_id=OuterRef('pk'),
                    answer__exact=fdata.get('answer')
                )
                qs = qs.annotate(has_answer=Exists(answers)).filter(has_answer=True)

        return qs


class FilterNullBooleanSelect(forms.NullBooleanSelect):
    def __init__(self, attrs=None):
        choices = (
            ('unknown', _('All')),
            ('true', _('Yes')),
            ('false', _('No')),
        )
        super(forms.NullBooleanSelect, self).__init__(attrs, choices)


class EventOrderExpertFilterForm(EventOrderFilterForm):
    subevents_from = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
        }),
        label=pgettext_lazy('subevent', 'All dates starting at or after'),
        required=False,
    )
    subevents_to = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
        }),
        label=pgettext_lazy('subevent', 'All dates starting before'),
        required=False,
    )
    created_from = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
        }),
        label=_('Order placed at or after'),
        required=False,
    )
    created_to = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
        }),
        label=_('Order placed before'),
        required=False,
    )
    email = forms.CharField(
        required=False,
        label=_('E-mail address')
    )
    comment = forms.CharField(
        required=False,
        label=_('Comment')
    )
    locale = forms.ChoiceField(
        required=False,
        label=_('Locale'),
        choices=settings.LANGUAGES
    )
    email_known_to_work = forms.NullBooleanField(
        required=False,
        widget=FilterNullBooleanSelect,
        label=_('E-mail address verified'),
    )
    total = forms.DecimalField(
        localize=True,
        required=False,
        label=_('Total amount'),
    )
    payment_sum_min = forms.DecimalField(
        localize=True,
        required=False,
        label=_('Minimal sum of payments and refunds'),
    )
    payment_sum_max = forms.DecimalField(
        localize=True,
        required=False,
        label=_('Maximal sum of payments and refunds'),
    )
    sales_channel = forms.ChoiceField(
        label=_('Sales channel'),
        required=False,
    )
    has_checkin = forms.NullBooleanField(
        required=False,
        widget=FilterNullBooleanSelect,
        label=_('At least one ticket with check-in'),
    )
    checkin_attention = forms.NullBooleanField(
        required=False,
        widget=FilterNullBooleanSelect,
        label=_('Requires special attention'),
        help_text=_('Only matches orders with the attention checkbox set directly for the order, not based on the product.'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields['query']
        del self.fields['question']
        del self.fields['answer']
        del self.fields['ordering']
        if not self.event.has_subevents:
            del self.fields['subevents_from']
            del self.fields['subevents_to']

        self.fields['sales_channel'].choices = [('', '')] + [
            (k, v.verbose_name) for k, v in get_all_sales_channels().items()
        ]

        locale_names = dict(settings.LANGUAGES)
        self.fields['locale'].choices = [('', '')] + [(a, locale_names[a]) for a in self.event.settings.locales]

        move_to_end(self.fields, 'item')
        move_to_end(self.fields, 'provider')

        self.fields['invoice_address_company'] = forms.CharField(
            required=False,
            label=gettext('Invoice address') + ': ' + gettext('Company')
        )
        self.fields['invoice_address_name'] = forms.CharField(
            required=False,
            label=gettext('Invoice address') + ': ' + gettext('Name')
        )
        self.fields['invoice_address_street'] = forms.CharField(
            required=False,
            label=gettext('Invoice address') + ': ' + gettext('Address')
        )
        self.fields['invoice_address_zipcode'] = forms.CharField(
            required=False,
            label=gettext('Invoice address') + ': ' + gettext('ZIP code'),
            help_text=_('Exact matches only')
        )
        self.fields['invoice_address_city'] = forms.CharField(
            required=False,
            label=gettext('Invoice address') + ': ' + gettext('City'),
            help_text=_('Exact matches only')
        )
        self.fields['invoice_address_country'] = forms.ChoiceField(
            required=False,
            label=gettext('Invoice address') + ': ' + gettext('Country'),
            choices=[('', '')] + list(CachedCountries())
        )
        self.fields['attendee_name'] = forms.CharField(
            required=False,
            label=_('Attendee name')
        )
        self.fields['attendee_email'] = forms.CharField(
            required=False,
            label=_('Attendee e-mail address')
        )
        self.fields['attendee_address_company'] = forms.CharField(
            required=False,
            label=gettext('Attendee address') + ': ' + gettext('Company')
        )
        self.fields['attendee_address_street'] = forms.CharField(
            required=False,
            label=gettext('Attendee address') + ': ' + gettext('Address')
        )
        self.fields['attendee_address_zipcode'] = forms.CharField(
            required=False,
            label=gettext('Attendee address') + ': ' + gettext('ZIP code'),
            help_text=_('Exact matches only')
        )
        self.fields['attendee_address_city'] = forms.CharField(
            required=False,
            label=gettext('Attendee address') + ': ' + gettext('City'),
            help_text=_('Exact matches only')
        )
        self.fields['attendee_address_country'] = forms.ChoiceField(
            required=False,
            label=gettext('Attendee address') + ': ' + gettext('Country'),
            choices=[('', '')] + list(CachedCountries())
        )
        self.fields['ticket_secret'] = forms.CharField(
            label=_('Ticket secret'),
            required=False
        )
        for q in self.event.questions.all():
            self.fields['question_{}'.format(q.pk)] = forms.CharField(
                label=q.question,
                required=False,
                help_text=_('Exact matches only')
            )

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        if fdata.get('subevents_from'):
            qs = qs.filter(
                all_positions__subevent__date_from__gte=fdata.get('subevents_from'),
                all_positions__canceled=False
            ).distinct()
        if fdata.get('subevents_to'):
            qs = qs.filter(
                all_positions__subevent__date_from__lt=fdata.get('subevents_to'),
                all_positions__canceled=False
            ).distinct()
        if fdata.get('email'):
            qs = qs.filter(
                email__icontains=fdata.get('email')
            )
        if fdata.get('created_from'):
            qs = qs.filter(datetime__gte=fdata.get('created_from'))
        if fdata.get('created_to'):
            qs = qs.filter(datetime__lte=fdata.get('created_to'))
        if fdata.get('comment'):
            qs = qs.filter(comment__icontains=fdata.get('comment'))
        if fdata.get('sales_channel'):
            qs = qs.filter(sales_channel=fdata.get('sales_channel'))
        if fdata.get('total'):
            qs = qs.filter(total=fdata.get('total'))
        if fdata.get('email_known_to_work') is not None:
            qs = qs.filter(email_known_to_work=fdata.get('email_known_to_work'))
        if fdata.get('checkin_attention') is not None:
            qs = qs.filter(checkin_attention=fdata.get('checkin_attention'))
        if fdata.get('locale'):
            qs = qs.filter(locale=fdata.get('locale'))
        if fdata.get('payment_sum_min') is not None:
            qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
            qs = qs.filter(
                computed_payment_refund_sum__gte=fdata['payment_sum_min'],
            )
        if fdata.get('payment_sum_max') is not None:
            qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
            qs = qs.filter(
                computed_payment_refund_sum__lte=fdata['payment_sum_max'],
            )
        if fdata.get('invoice_address_company'):
            qs = qs.filter(invoice_address__company__icontains=fdata.get('invoice_address_company'))
        if fdata.get('invoice_address_name'):
            qs = qs.filter(invoice_address__name_cached__icontains=fdata.get('invoice_address_name'))
        if fdata.get('invoice_address_street'):
            qs = qs.filter(invoice_address__street__icontains=fdata.get('invoice_address_street'))
        if fdata.get('invoice_address_zipcode'):
            qs = qs.filter(invoice_address__zipcode__iexact=fdata.get('invoice_address_zipcode'))
        if fdata.get('invoice_address_city'):
            qs = qs.filter(invoice_address__city__iexact=fdata.get('invoice_address_city'))
        if fdata.get('invoice_address_country'):
            qs = qs.filter(invoice_address__country=fdata.get('invoice_address_country'))
        if fdata.get('attendee_name'):
            qs = qs.filter(
                all_positions__attendee_name_cached__icontains=fdata.get('attendee_name')
            )
        if fdata.get('attendee_address_company'):
            qs = qs.filter(
                all_positions__company__icontains=fdata.get('attendee_address_company')
            ).distinct()
        if fdata.get('attendee_address_street'):
            qs = qs.filter(
                all_positions__street__icontains=fdata.get('attendee_address_street')
            ).distinct()
        if fdata.get('attendee_address_city'):
            qs = qs.filter(
                all_positions__city__iexact=fdata.get('attendee_address_city')
            ).distinct()
        if fdata.get('attendee_address_country'):
            qs = qs.filter(
                all_positions__country=fdata.get('attendee_address_country')
            ).distinct()
        if fdata.get('has_checkin') is not None:
            qs = qs.annotate(
                has_checkin=Exists(
                    Checkin.all.filter(position__order_id=OuterRef('pk'))
                )
            ).filter(has_checkin=fdata['has_checkin'])
        if fdata.get('ticket_secret'):
            qs = qs.filter(
                all_positions__secret__icontains=fdata.get('ticket_secret')
            ).distinct()
        for q in self.event.questions.all():
            if fdata.get(f'question_{q.pk}'):
                answers = QuestionAnswer.objects.filter(
                    question_id=q.pk,
                    orderposition__order_id=OuterRef('pk'),
                    answer__iexact=fdata.get(f'question_{q.pk}')
                )
                qs = qs.annotate(**{f'q_{q.pk}': Exists(answers)}).filter(**{f'q_{q.pk}': True})

        return qs


class OrderSearchFilterForm(OrderFilterForm):
    orders = {'code': 'code', 'email': 'email', 'total': 'total',
              'datetime': 'datetime', 'status': 'status',
              'event': 'event'}

    organizer = forms.ModelChoiceField(
        label=_('Organizer'),
        queryset=Organizer.objects.none(),
        required=False,
        empty_label=_('All organizers'),
        widget=Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse_lazy('control:organizers.select2'),
                'data-placeholder': _('All organizers')
            }
        )
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        if self.request.user.has_active_staff_session(self.request.session.session_key):
            self.fields['organizer'].queryset = Organizer.objects.all()
        else:
            self.fields['organizer'].queryset = Organizer.objects.filter(
                pk__in=self.request.user.teams.values_list('organizer', flat=True)
            )
        self.fields['provider'].choices += get_all_payment_providers()

        seen = set()
        for p in self.meta_properties.all():
            if p.name in seen:
                continue
            seen.add(p.name)
            self.fields['meta_{}'.format(p.name)] = forms.CharField(
                label=p.name,
                required=False,
                widget=forms.TextInput(
                    attrs={
                        'data-typeahead-url': reverse('control:events.meta.typeahead') + '?' + urlencode({
                            'property': p.name,
                            'organizer': ''
                        })
                    }
                )
            )

    def use_query_hack(self):
        return (
            self.cleaned_data.get('query') or
            self.cleaned_data.get('status') in ('overpaid', 'partially_paid', 'underpaid', 'pendingpaid')
        )

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        if fdata.get('organizer'):
            qs = qs.filter(event__organizer=fdata.get('organizer'))

        filters_by_property_name = {}
        for i, p in enumerate(self.meta_properties):
            d = fdata.get('meta_{}'.format(p.name))
            if d:
                emv_with_value = EventMetaValue.objects.filter(
                    event=OuterRef('event_id'),
                    property__pk=p.pk,
                    value=d
                )
                emv_with_any_value = EventMetaValue.objects.filter(
                    event=OuterRef('event_id'),
                    property__pk=p.pk,
                )
                qs = qs.annotate(**{'attr_{}'.format(i): Exists(emv_with_value)})
                if p.name in filters_by_property_name:
                    filters_by_property_name[p.name] |= Q(**{'attr_{}'.format(i): True})
                else:
                    filters_by_property_name[p.name] = Q(**{'attr_{}'.format(i): True})
                if p.default == d:
                    qs = qs.annotate(**{'attr_{}_any'.format(i): Exists(emv_with_any_value)})
                    filters_by_property_name[p.name] |= Q(**{
                        'attr_{}_any'.format(i): False, 'event__organizer_id': p.organizer_id
                    })
        for f in filters_by_property_name.values():
            qs = qs.filter(f)

        return qs

    @cached_property
    def meta_properties(self):
        # We ignore superuser permissions here. This is intentional – we do not want to show super
        # users a form with all meta properties ever assigned.
        return EventMetaProperty.objects.filter(
            organizer_id__in=self.request.user.teams.values_list('organizer', flat=True),
            filter_allowed=True,
        )


class OrderPaymentSearchFilterForm(forms.Form):
    orders = {'id': 'id', 'local_id': 'local_id', 'state': 'state', 'amount': 'amount', 'order': 'order',
              'created': 'created', 'payment_date': 'payment_date', 'provider': 'provider', 'info': 'info',
              'fee': 'fee'}

    query = forms.CharField(
        label=_('Search for…'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search for…'),
            'autofocus': 'autofocus'
        }),
        required=False,
    )
    event = forms.ModelChoiceField(
        label=_('Event'),
        queryset=Event.objects.none(),
        required=False,
        widget=Select2(
            attrs={
                'data-model-select2': 'event',
                'data-select2-url': reverse_lazy('control:events.typeahead'),
                'data-placeholder': _('All events')
            }
        )
    )
    organizer = forms.ModelChoiceField(
        label=_('Organizer'),
        queryset=Organizer.objects.none(),
        required=False,
        empty_label=_('All organizers'),
        widget=Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse_lazy('control:organizers.select2'),
                'data-placeholder': _('All organizers')
            }
        ),
    )
    state = forms.ChoiceField(
        label=_('Status'),
        required=False,
        choices=[('', _('All payments'))] + list(OrderPayment.PAYMENT_STATES),
    )
    provider = forms.ChoiceField(
        label=_('Payment provider'),
        choices=[
            ('', _('All payment providers')),
        ],
        required=False,
    )
    created_from = forms.DateField(
        label=_('Payment created from'),
        required=False,
        widget=DatePickerWidget,
    )
    created_until = forms.DateField(
        label=_('Payment created until'),
        required=False,
        widget=DatePickerWidget,
    )
    completed_from = forms.DateField(
        label=_('Paid from'),
        required=False,
        widget=DatePickerWidget,
    )
    completed_until = forms.DateField(
        label=_('Paid until'),
        required=False,
        widget=DatePickerWidget,
    )
    amount = forms.CharField(
        label=_('Amount'),
        required=False,
        widget=forms.NumberInput(attrs={
            'placeholder': _('Amount'),
        }),
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        self.fields['ordering'] = forms.ChoiceField(
            choices=sum([
                [(a, a), ('-' + a, '-' + a)]
                for a in self.orders.keys()
            ], []),
            required=False
        )

        if self.request.user.has_active_staff_session(self.request.session.session_key):
            self.fields['organizer'].queryset = Organizer.objects.all()
            self.fields['event'].queryset = Event.objects.all()

        else:
            self.fields['organizer'].queryset = Organizer.objects.filter(
                pk__in=self.request.user.teams.values_list('organizer', flat=True)
            )
            self.fields['event'].queryset = self.request.user.get_events_with_permission('can_view_orders')

        self.fields['provider'].choices += get_all_payment_providers()

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('created_from'):
            date_start = make_aware(datetime.combine(
                fdata.get('created_from'),
                time(hour=0, minute=0, second=0, microsecond=0)
            ), get_current_timezone())
            qs = qs.filter(created__gte=date_start)

        if fdata.get('created_until'):
            date_end = make_aware(datetime.combine(
                fdata.get('created_until') + timedelta(days=1),
                time(hour=0, minute=0, second=0, microsecond=0)
            ), get_current_timezone())
            qs = qs.filter(created__lt=date_end)

        if fdata.get('completed_from'):
            date_start = make_aware(datetime.combine(
                fdata.get('completed_from'),
                time(hour=0, minute=0, second=0, microsecond=0)
            ), get_current_timezone())
            qs = qs.filter(payment_date__gte=date_start)

        if fdata.get('completed_until'):
            date_end = make_aware(datetime.combine(
                fdata.get('completed_until') + timedelta(days=1),
                time(hour=0, minute=0, second=0, microsecond=0)
            ), get_current_timezone())
            qs = qs.filter(payment_date__lt=date_end)

        if fdata.get('event'):
            qs = qs.filter(order__event=fdata.get('event'))

        if fdata.get('organizer'):
            qs = qs.filter(order__event__organizer=fdata.get('organizer'))

        if fdata.get('state'):
            qs = qs.filter(state=fdata.get('state'))

        if fdata.get('provider'):
            qs = qs.filter(provider=fdata.get('provider'))

        if fdata.get('query'):
            u = fdata.get('query')

            invoice_nos = {u, u.upper()}
            if u.isdigit():
                for i in range(2, 12):
                    invoice_nos.add(u.zfill(i))

            matching_invoices = Invoice.objects.filter(
                Q(invoice_no__in=invoice_nos)
                | Q(full_invoice_no__iexact=u)
            ).values_list('order_id', flat=True)

            matching_invoice_addresses = InvoiceAddress.objects.filter(
                Q(
                    Q(name_cached__icontains=u) | Q(company__icontains=u)
                )
            ).values_list('order_id', flat=True)

            if "-" in u:
                code = (Q(event__slug__icontains=u.rsplit("-", 1)[0])
                        & Q(code__icontains=Order.normalize_code(u.rsplit("-", 1)[1])))
            else:
                code = Q(code__icontains=Order.normalize_code(u))

            matching_orders = Order.objects.filter(
                Q(
                    code
                    | Q(email__icontains=u)
                    | Q(comment__icontains=u)
                )
            ).values_list('id', flat=True)

            mainq = (
                Q(order__id__in=matching_invoices)
                | Q(order__id__in=matching_invoice_addresses)
                | Q(order__id__in=matching_orders)
            )

            qs = qs.filter(mainq)

        if fdata.get('amount'):
            amount = fdata.get('amount')

            def is_decimal(value):
                result = True
                parts = value.split('.', maxsplit=1)
                for part in parts:
                    result = result & part.isdecimal()
                return result

            if is_decimal(amount):
                qs = qs.filter(amount=Decimal(amount))

        if fdata.get('ordering'):
            p = self.cleaned_data.get('ordering')
            if p.startswith('-') and p not in self.orders:
                qs = qs.order_by(*get_deterministic_ordering(OrderPayment, '-' + self.orders[p[1:]]))
            else:
                qs = qs.order_by(*get_deterministic_ordering(OrderPayment, self.orders[p]))
        else:
            qs = qs.order_by('-created', '-pk')

        return qs


class SubEventFilterForm(FilterForm):
    orders = {
        'date_from': 'date_from',
        'active': 'active',
        'sum_quota_available': 'sum_quota_available'
    }
    status = forms.ChoiceField(
        label=_('Status'),
        choices=(
            ('', _('All')),
            ('active', _('Active')),
            ('running', _('Shop live and presale running')),
            ('inactive', _('Inactive')),
            ('future', _('Presale not started')),
            ('past', _('Presale over')),
        ),
        required=False
    )
    date_from = forms.DateField(
        label=_('Date from'),
        required=False,
        widget=DatePickerWidget({
            'placeholder': _('Date from'),
        }),
    )
    date_until = forms.DateField(
        label=_('Date until'),
        required=False,
        widget=DatePickerWidget({
            'placeholder': _('Date until'),
        }),
    )
    time_from = forms.TimeField(
        label=_('Start time from'),
        required=False,
        widget=TimePickerWidget({}),
    )
    time_until = forms.TimeField(
        label=_('Start time until'),
        required=False,
        widget=TimePickerWidget({}),
    )
    weekday = forms.MultipleChoiceField(
        label=_('Weekday'),
        choices=(
            ('2', _('Monday')),
            ('3', _('Tuesday')),
            ('4', _('Wednesday')),
            ('5', _('Thursday')),
            ('6', _('Friday')),
            ('7', _('Saturday')),
            ('1', _('Sunday')),
        ),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )
    query = forms.CharField(
        label=_('Event name'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Event name'),
            'autofocus': 'autofocus'
        }),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['date_from'].widget = DatePickerWidget()
        self.fields['date_until'].widget = DatePickerWidget()
        for p in self.meta_properties.all():
            self.fields['meta_{}'.format(p.name)] = forms.CharField(
                label=p.name,
                required=False,
                widget=forms.TextInput(
                    attrs={
                        'data-typeahead-url': reverse('control:event.subevents.meta.typeahead', kwargs={
                            'organizer': self.event.organizer.slug,
                            'event': self.event.slug
                        }) + '?' + urlencode({
                            'property': p.name,
                        })
                    }
                )
            )

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('status') == 'active':
            qs = qs.filter(active=True)
        elif fdata.get('status') == 'running':
            qs = qs.filter(
                active=True
            ).filter(
                Q(presale_start__isnull=True) | Q(presale_start__lte=now())
            ).filter(
                Q(Q(presale_end__isnull=True) & Q(
                    Q(date_to__gte=now()) |
                    Q(date_to__isnull=True, date_from__gte=now())
                )) |
                Q(presale_end__gte=now())
            )
        elif fdata.get('status') == 'inactive':
            qs = qs.filter(active=False)
        elif fdata.get('status') == 'future':
            qs = qs.filter(presale_start__gte=now())
        elif fdata.get('status') == 'past':
            qs = qs.filter(
                Q(presale_end__lte=now()) | Q(
                    Q(presale_end__isnull=True) & Q(
                        Q(date_to__lte=now()) |
                        Q(date_to__isnull=True, date_from__gte=now())
                    )
                )
            )

        if fdata.get('weekday'):
            qs = qs.annotate(wday=ExtractWeekDay('date_from')).filter(wday__in=fdata.get('weekday'))

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(name__icontains=i18ncomp(query)) | Q(location__icontains=query)
            )

        if fdata.get('date_until'):
            date_end = make_aware(datetime.combine(
                fdata.get('date_until') + timedelta(days=1),
                time(hour=0, minute=0, second=0, microsecond=0)
            ), get_current_timezone())
            qs = qs.filter(
                Q(date_to__isnull=True, date_from__lt=date_end) |
                Q(date_to__isnull=False, date_to__lt=date_end)
            )
        if fdata.get('date_from'):
            date_start = make_aware(datetime.combine(
                fdata.get('date_from'),
                time(hour=0, minute=0, second=0, microsecond=0)
            ), get_current_timezone())
            qs = qs.filter(date_from__gte=date_start)

        if fdata.get('time_until'):
            qs = qs.filter(date_from__time__lte=fdata.get('time_until'))
        if fdata.get('time_from'):
            qs = qs.filter(date_from__time__gte=fdata.get('time_from'))

        filters_by_property_name = {}
        for i, p in enumerate(self.meta_properties):
            d = fdata.get('meta_{}'.format(p.name))
            if d:
                semv_with_value = SubEventMetaValue.objects.filter(
                    subevent=OuterRef('pk'),
                    property__pk=p.pk,
                    value=d
                )
                semv_with_any_value = SubEventMetaValue.objects.filter(
                    subevent=OuterRef('pk'),
                    property__pk=p.pk,
                )
                qs = qs.annotate(**{'attr_{}'.format(i): Exists(semv_with_value)})
                if p.name in filters_by_property_name:
                    filters_by_property_name[p.name] |= Q(**{'attr_{}'.format(i): True})
                else:
                    filters_by_property_name[p.name] = Q(**{'attr_{}'.format(i): True})
                default = self.event.meta_data[p.name]
                if default == d:
                    qs = qs.annotate(**{'attr_{}_any'.format(i): Exists(semv_with_any_value)})
                    filters_by_property_name[p.name] |= Q(**{'attr_{}_any'.format(i): False})
        for f in filters_by_property_name.values():
            qs = qs.filter(f)

        if fdata.get('ordering'):
            qs = qs.order_by(*get_deterministic_ordering(SubEvent, self.get_order_by()))
        else:
            qs = qs.order_by('-date_from', '-pk')

        return qs

    @cached_property
    def meta_properties(self):
        return self.event.organizer.meta_properties.filter(filter_allowed=True)


class OrganizerFilterForm(FilterForm):
    orders = {
        'slug': 'slug',
        'name': 'name',
    }
    query = forms.CharField(
        label=_('Organizer name'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Organizer name'),
            'autofocus': 'autofocus'
        }),
        required=False
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(name__icontains=query) | Q(slug__icontains=query)
            )

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())

        return qs


class GiftCardFilterForm(FilterForm):
    orders = {
        'issuance': 'issuance',
        'expires': F('expires').asc(nulls_last=True),
        '-expires': F('expires').desc(nulls_first=True),
        'secret': 'secret',
        'value': 'cached_value',
    }
    testmode = forms.ChoiceField(
        label=_('Test mode'),
        choices=(
            ('', _('All')),
            ('yes', _('Test mode')),
            ('no', _('Live')),
        ),
        required=False
    )
    state = forms.ChoiceField(
        label=_('Status'),
        choices=(
            ('', _('All')),
            ('empty', _('Empty')),
            ('valid_value', _('Valid and with value')),
            ('expired_value', _('Expired and with value')),
            ('expired', _('Expired')),
        ),
        required=False
    )
    query = forms.CharField(
        label=_('Search query'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search query'),
            'autofocus': 'autofocus'
        }),
        required=False
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(secret__icontains=query)
                | Q(transactions__text__icontains=query)
                | Q(transactions__order__code__icontains=query)
                | Q(owner_ticket__order__code__icontains=query)
            )
        if fdata.get('testmode') == 'yes':
            qs = qs.filter(testmode=True)
        elif fdata.get('testmode') == 'no':
            qs = qs.filter(testmode=False)
        if fdata.get('state') == 'empty':
            qs = qs.filter(cached_value=0)
        elif fdata.get('state') == 'valid_value':
            qs = qs.exclude(cached_value=0).filter(Q(expires__isnull=True) | Q(expires__gte=now()))
        elif fdata.get('state') == 'expired_value':
            qs = qs.exclude(cached_value=0).filter(expires__lt=now())
        elif fdata.get('state') == 'expired':
            qs = qs.filter(expires__lt=now())

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())
        else:
            qs = qs.order_by('-issuance')

        return qs.distinct()


class CustomerFilterForm(FilterForm):
    orders = {
        'email': 'email',
        'identifier': 'identifier',
        'name': 'name_cached',
        'external_identifier': 'external_identifier',
    }
    query = forms.CharField(
        label=_('Search query'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search query'),
            'autofocus': 'autofocus'
        }),
        required=False
    )
    status = forms.ChoiceField(
        label=_('Status'),
        required=False,
        choices=(
            ('', _('All')),
            ('active', _('active')),
            ('disabled', _('disabled')),
            ('unverified', _('not yet activated')),
        )
    )
    memberships = forms.ChoiceField(
        label=_('Memberships'),
        required=False,
        choices=(
            ('', _('All')),
            ('no', _('Has no memberships')),
            ('any', _('Has any membership')),
            ('valid', _('Has valid membership')),
        )
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(email__icontains=query)
                | Q(name_cached__icontains=query)
                | Q(identifier__istartswith=query)
                | Q(external_identifier__icontains=query)
                | Q(notes__icontains=query)
            )

        if fdata.get('status') == 'active':
            qs = qs.filter(is_active=True, is_verified=True)
        elif fdata.get('status') == 'disabled':
            qs = qs.filter(is_active=False)
        elif fdata.get('status') == 'unverified':
            qs = qs.filter(is_verified=False)

        if fdata.get('memberships') == 'no':
            qs = qs.filter(memberships__isnull=True)
        elif fdata.get('memberships') == 'any':
            qs = qs.filter(memberships__isnull=False)
        elif fdata.get('memberships') == 'valid':
            qs = qs.filter(memberships__date_start__lt=now(), memberships__date_end__gt=now(), memberships__canceled=False)

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())
        else:
            qs = qs.order_by('-email')

        return qs.distinct()


class ReusableMediaFilterForm(FilterForm):
    orders = {
        'type': 'type',
        'identifier': 'identifier',
    }
    query = forms.CharField(
        label=_('Search query'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search query'),
            'autofocus': 'autofocus'
        }),
        required=False
    )
    status = forms.ChoiceField(
        label=_('Status'),
        required=False,
        choices=(
            ('', _('All')),
            ('active', _('active')),
            ('disabled', _('disabled')),
            ('expired', _('expired')),
        )
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(identifier__icontains=query)
                | Q(customer__identifier__icontains=query)
                | Q(customer__external_identifier__istartswith=query)
                | Q(linked_orderposition__order__code__icontains=query)
                | Q(linked_giftcard__secret__icontains=query)
            )

        if fdata.get('status') == 'active':
            qs = qs.filter(Q(expires__gt=now()) | Q(expires__isnull=False), active=True)
        elif fdata.get('status') == 'disabled':
            qs = qs.filter(active=False)
        elif fdata.get('status') == 'expired':
            qs = qs.filter(expires__lte=now())

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())
        else:
            qs = qs.order_by("identifier", "type", "organizer")

        return qs.distinct()


class TeamFilterForm(FilterForm):
    orders = {
        'name': 'name',
    }
    query = forms.CharField(
        label=_('Search query'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search query'),
            'autofocus': 'autofocus'
        }),
        required=False
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(Exists(
                    Team.members.through.objects.filter(
                        Q(user__email__icontains=query) | Q(user__fullname__icontains=query),
                        team_id=OuterRef('pk'),
                    )
                ))
                | Q(Exists(
                    TeamInvite.objects.filter(
                        email__icontains=query,
                        team_id=OuterRef('pk'),
                    )
                ))
                | Q(Exists(
                    TeamAPIToken.objects.filter(
                        name__icontains=query,
                        team_id=OuterRef('pk'),
                    )
                ))
                | Q(name__icontains=query)
            )

        if fdata.get('ordering'):
            qs = qs.order_by(*get_deterministic_ordering(Team, self.get_order_by()))

        return qs.distinct()


class EventFilterForm(FilterForm):
    orders = {
        'slug': 'slug',
        'organizer': 'organizer__name',
        'date_from': 'order_from',
        'date_to': 'order_to',
        'live': 'live',
    }
    status = forms.ChoiceField(
        label=_('Status'),
        choices=(
            ('', _('All events')),
            ('live', _('Shop live')),
            ('running', _('Shop live and presale running')),
            ('notlive', _('Shop not live')),
            ('future', _('Presale not started')),
            ('past', _('Presale over')),
            ('date_future', _('Single event running or in the future')),
            ('date_past', _('Single event in the past')),
            ('series', _('Event series')),
        ),
        required=False
    )
    organizer = forms.ModelChoiceField(
        label=_('Organizer'),
        queryset=Organizer.objects.none(),
        required=False,
        empty_label=_('All organizers'),
        widget=Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse_lazy('control:organizers.select2'),
                'data-placeholder': _('All organizers')
            }
        )
    )
    query = forms.CharField(
        label=_('Event name'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Event name'),
            'autofocus': 'autofocus'
        }),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        self.organizer = kwargs.pop('organizer', None)
        super().__init__(*args, **kwargs)
        seen = set()
        for p in self.meta_properties.all():
            if p.name in seen:
                continue
            seen.add(p.name)
            self.fields['meta_{}'.format(p.name)] = forms.CharField(
                label=p.name,
                required=False,
                widget=forms.TextInput(
                    attrs={
                        'data-typeahead-url': reverse('control:events.meta.typeahead') + '?' + urlencode({
                            'property': p.name,
                            'organizer': self.organizer.slug if self.organizer else ''
                        })
                    }
                )
            )
        if self.organizer:
            del self.fields['organizer']
        else:
            if self.request.user.has_active_staff_session(self.request.session.session_key):
                self.fields['organizer'].queryset = Organizer.objects.all()
            else:
                self.fields['organizer'].queryset = Organizer.objects.filter(
                    pk__in=self.request.user.teams.values_list('organizer', flat=True)
                )

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('status') == 'live':
            qs = qs.filter(live=True)
        elif fdata.get('status') == 'running':
            qs = qs.filter(
                live=True
            ).annotate(
                p_end=Coalesce(F('presale_end'), F('date_to'), F('date_from'))
            ).filter(
                Q(presale_start__isnull=True) | Q(presale_start__lte=now())
            ).filter(
                Q(p_end__gte=now())
            )
        elif fdata.get('status') == 'notlive':
            qs = qs.filter(live=False)
        elif fdata.get('status') == 'future':
            qs = qs.filter(presale_start__gte=now())
        elif fdata.get('status') == 'past':
            qs = qs.filter(presale_end__lte=now())
        elif fdata.get('status') == 'date_future':
            qs = qs.filter(
                Q(has_subevents=False) &
                Q(
                    Q(Q(date_to__isnull=True) & Q(date_from__gte=now()))
                    | Q(Q(date_to__isnull=False) & Q(date_to__gte=now()))
                )
            )
        elif fdata.get('status') == 'date_past':
            qs = qs.filter(
                Q(has_subevents=False) &
                Q(
                    Q(Q(date_to__isnull=True) & Q(date_from__lt=now()))
                    | Q(Q(date_to__isnull=False) & Q(date_to__lt=now()))
                )
            )
        elif fdata.get('status') == 'series':
            qs = qs.filter(has_subevents=True)

        if fdata.get('organizer'):
            qs = qs.filter(organizer=fdata.get('organizer'))

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(name__icontains=i18ncomp(query)) | Q(slug__icontains=query)
            )

        filters_by_property_name = {}
        for i, p in enumerate(self.meta_properties):
            d = fdata.get('meta_{}'.format(p.name))
            if d:
                emv_with_value = EventMetaValue.objects.filter(
                    event=OuterRef('pk'),
                    property__pk=p.pk,
                    value=d
                )
                emv_with_any_value = EventMetaValue.objects.filter(
                    event=OuterRef('pk'),
                    property__pk=p.pk,
                )
                qs = qs.annotate(**{'attr_{}'.format(i): Exists(emv_with_value)})
                if p.name in filters_by_property_name:
                    filters_by_property_name[p.name] |= Q(**{'attr_{}'.format(i): True})
                else:
                    filters_by_property_name[p.name] = Q(**{'attr_{}'.format(i): True})
                if p.default == d:
                    qs = qs.annotate(**{'attr_{}_any'.format(i): Exists(emv_with_any_value)})
                    filters_by_property_name[p.name] |= Q(**{'attr_{}_any'.format(i): False, 'organizer_id': p.organizer_id})
        for f in filters_by_property_name.values():
            qs = qs.filter(f)

        if fdata.get('ordering'):
            qs = qs.order_by(*get_deterministic_ordering(Event, self.get_order_by()))

        return qs

    @cached_property
    def meta_properties(self):
        if self.organizer:
            return self.organizer.meta_properties.filter(filter_allowed=True)
        else:
            # We ignore superuser permissions here. This is intentional – we do not want to show super
            # users a form with all meta properties ever assigned.
            return EventMetaProperty.objects.filter(
                organizer_id__in=self.request.user.teams.values_list('organizer', flat=True),
                filter_allowed=True,
            )


class CheckinListAttendeeFilterForm(FilterForm):
    orders = {
        'code': ('order__code', 'item__name'),
        '-code': ('-order__code', '-item__name'),
        'email': ('order__email', 'item__name'),
        '-email': ('-order__email', '-item__name'),
        'status': (OrderBy(F('last_entry'), nulls_first=True, descending=True), 'order__code'),
        '-status': (OrderBy(F('last_entry'), nulls_last=True), '-order__code'),
        'timestamp': (OrderBy(F('last_entry'), nulls_first=True), 'order__code'),
        '-timestamp': (OrderBy(F('last_entry'), nulls_last=True, descending=True), '-order__code'),
        'item': ('item__name', 'variation__value', 'order__code'),
        '-item': ('-item__name', '-variation__value', '-order__code'),
        'seat': ('seat__sorting_rank', 'seat__guid'),
        '-seat': ('-seat__sorting_rank', '-seat__guid'),
        'date': ('subevent__date_from', 'subevent__id', 'order__code'),
        '-date': ('-subevent__date_from', 'subevent__id', '-order__code'),
        'name': {'_order': F('display_name').asc(nulls_first=True),
                 'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')},
        '-name': {'_order': F('display_name').desc(nulls_last=True),
                  'display_name': Coalesce('attendee_name_cached', 'addon_to__attendee_name_cached')},
    }

    user = forms.CharField(
        label=_('Search attendee…'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search attendee…'),
            'autofocus': 'autofocus'
        }),
        required=False
    )
    status = forms.ChoiceField(
        label=_('Check-in status'),
        choices=(
            ('', _('All attendees')),
            ('1', _('Checked in')),
            ('2', pgettext_lazy('checkin state', 'Present')),
            ('3', pgettext_lazy('checkin state', 'Checked in but left')),
            ('0', _('Not checked in')),
        ),
        required=False,
    )
    item = forms.ModelChoiceField(
        label=_('Products'),
        queryset=Item.objects.none(),
        required=False,
        empty_label=_('All products')
    )
    subevent = forms.ModelChoiceField(
        label=pgettext_lazy('subevent', 'Date'),
        queryset=SubEvent.objects.none(),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )
    subevent_from = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
        }),
        label=pgettext_lazy('subevent', 'Date start from'),
        required=False,
    )
    subevent_until = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
        }),
        label=pgettext_lazy('subevent', 'Date start until'),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        self.list = kwargs.pop('list')
        super().__init__(*args, **kwargs)
        if self.list.all_products:
            self.fields['item'].queryset = self.event.items.all()
        else:
            self.fields['item'].queryset = self.list.limit_products.all()

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        else:
            del self.fields['subevent']
            del self.fields['subevent_from']
            del self.fields['subevent_until']

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('user'):
            u = fdata.get('user')
            qs = qs.filter(
                Q(order__code__istartswith=u)
                | Q(secret__istartswith=u)
                | Q(pseudonymization_id__istartswith=u)
                | Q(order__email__icontains=u)
                | Q(attendee_name_cached__icontains=u)
                | Q(attendee_email__icontains=u)
                | Q(voucher__code__istartswith=u)
                | Q(order__invoice_address__name_cached__icontains=u)
                | Q(order__invoice_address__company__icontains=u)
            )

        if fdata.get('status'):
            s = fdata.get('status')
            if s == '1':
                qs = qs.filter(last_entry__isnull=False)
            elif s == '2':
                qs = qs.filter(pk__in=self.list.positions_inside.values_list('pk'))
            elif s == '3':
                qs = qs.filter(last_entry__isnull=False).filter(
                    Q(last_exit__isnull=False) & Q(last_exit__gte=F('last_entry'))
                )
            elif s == '0':
                qs = qs.filter(last_entry__isnull=True)

        if fdata.get('ordering'):
            ob = self.orders[fdata.get('ordering')]
            if isinstance(ob, dict):
                ob = dict(ob)
                o = ob.pop('_order')
                qs = qs.annotate(**ob).order_by(*get_deterministic_ordering(OrderPosition, [o]))
            elif isinstance(ob, (list, tuple)):
                qs = qs.order_by(*get_deterministic_ordering(OrderPosition, ob))
            else:
                qs = qs.order_by(*get_deterministic_ordering(OrderPosition, [ob]))

        if fdata.get('item'):
            qs = qs.filter(item=fdata.get('item'))

        if fdata.get('subevent'):
            qs = qs.filter(subevent_id=fdata.get('subevent').pk)

        if fdata.get('subevent_from'):
            qs = qs.filter(subevent__date_from__gte=fdata.get('subevent_from'))
        if fdata.get('subevent_until'):
            qs = qs.filter(subevent__date_from__lte=fdata.get('subevent_until'))

        return qs


class UserFilterForm(FilterForm):
    orders = {
        'fullname': 'fullname',
        'email': 'email',
    }
    status = forms.ChoiceField(
        label=_('Status'),
        choices=(
            ('', _('All')),
            ('active', _('Active')),
            ('inactive', _('Inactive')),
        ),
        required=False
    )
    superuser = forms.ChoiceField(
        label=_('Administrator'),
        choices=(
            ('', _('All')),
            ('yes', _('Administrator')),
            ('no', _('No administrator')),
        ),
        required=False
    )
    query = forms.CharField(
        label=_('Search query'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search query'),
            'autofocus': 'autofocus'
        }),
        required=False
    )

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('status') == 'active':
            qs = qs.filter(is_active=True)
        elif fdata.get('status') == 'inactive':
            qs = qs.filter(is_active=False)

        if fdata.get('superuser') == 'yes':
            qs = qs.filter(is_staff=True)
        elif fdata.get('superuser') == 'no':
            qs = qs.filter(is_staff=False)

        if fdata.get('query'):
            qs = qs.filter(
                Q(email__icontains=fdata.get('query'))
                | Q(fullname__icontains=fdata.get('query'))
            )

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())

        return qs


class VoucherFilterForm(FilterForm):
    orders = {
        'code': 'code',
        '-code': '-code',
        'redeemed': 'redeemed',
        '-redeemed': '-redeemed',
        'valid_until': 'valid_until',
        '-valid_until': '-valid_until',
        'tag': 'tag',
        '-tag': '-tag',
        'item': (
            'seat__sorting_rank',
            'item__category__position',
            'item__category',
            'item__position',
            'item__variation__position',
            'quota__name',
        ),
        'subevent': 'subevent__date_from',
        '-subevent': '-subevent__date_from',
        '-item': (
            '-seat__sorting_rank',
            '-item__category__position',
            '-item__category',
            '-item__position',
            '-item__variation__position',
            '-quota__name',
        )
    }
    status = forms.ChoiceField(
        label=_('Status'),
        choices=(
            ('', _('All')),
            ('v', _('Valid')),
            ('u', _('Unredeemed')),
            ('r', _('Redeemed at least once')),
            ('f', _('Fully redeemed')),
            ('e', _('Expired')),
            ('c', _('Redeemed and checked in with ticket')),
        ),
        required=False
    )
    qm = forms.ChoiceField(
        label=_('Quota handling'),
        choices=(
            ('', _('All')),
            ('b', _('Reserve ticket from quota')),
            ('i', _('Allow to ignore quota')),
        ),
        required=False
    )
    tag = forms.CharField(
        label=_('Filter by tag'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Filter by tag'),
        }),
        required=False
    )
    search = forms.CharField(
        label=_('Search voucher'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search voucher'),
            'autofocus': 'autofocus'
        }),
        required=False
    )
    subevent = forms.ModelChoiceField(
        label=pgettext_lazy('subevent', 'Date'),
        queryset=SubEvent.objects.none(),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )
    itemvar = forms.ChoiceField(
        label=_("Product"),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        elif 'subevent':
            del self.fields['subevent']

        choices = [('', _('All products'))]
        for i in self.event.items.prefetch_related('variations').all():
            variations = list(i.variations.all())
            if variations:
                choices.append((str(i.pk), _('{product} – Any variation').format(product=str(i))))
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (str(i), v.value)))
            else:
                choices.append((str(i.pk), str(i)))
        for q in self.event.quotas.all():
            choices.append(('q-%d' % q.pk, _('Any product in quota "{quota}"').format(quota=q)))
        self.fields['itemvar'].choices = choices

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('search'):
            s = fdata.get('search').strip()
            qs = qs.filter(Q(code__icontains=s) | Q(tag__icontains=s) | Q(comment__icontains=s))

        if fdata.get('tag'):
            s = fdata.get('tag').strip()
            if s == '<>':
                qs = qs.filter(Q(tag__isnull=True) | Q(tag=''))
            elif s[0] == '"' and s[-1] == '"':
                qs = qs.filter(tag__exact=s[1:-1])
            else:
                qs = qs.filter(tag__icontains=s)

        if fdata.get('qm'):
            s = fdata.get('qm')
            if s == 'b':
                qs = qs.filter(block_quota=True)
            elif s == 'i':
                qs = qs.filter(allow_ignore_quota=True)

        if fdata.get('status'):
            s = fdata.get('status')
            if s == 'v':
                qs = qs.filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now())).filter(redeemed__lt=F('max_usages'))
            elif s == 'r':
                qs = qs.filter(redeemed__gt=0)
            elif s == 'u':
                qs = qs.filter(redeemed=0)
            elif s == 'f':
                qs = qs.filter(redeemed__gte=F('max_usages'))
            elif s == 'e':
                qs = qs.filter(Q(valid_until__isnull=False) & Q(valid_until__lt=now())).filter(redeemed=0)
            elif s == 'c':
                checkins = Checkin.objects.filter(
                    position__voucher=OuterRef('pk')
                )
                qs = qs.annotate(has_checkin=Exists(checkins)).filter(
                    redeemed__gt=0, has_checkin=True
                )

        if fdata.get('itemvar'):
            if fdata.get('itemvar').startswith('q-'):
                qs = qs.filter(quota_id=fdata.get('itemvar').split('-')[1])
            elif '-' in fdata.get('itemvar'):
                qs = qs.filter(item_id=fdata.get('itemvar').split('-')[0],
                               variation_id=fdata.get('itemvar').split('-')[1])
            else:
                qs = qs.filter(item_id=fdata.get('itemvar'))

        if fdata.get('subevent'):
            qs = qs.filter(subevent_id=fdata.get('subevent').pk)

        if fdata.get('ordering'):
            ob = self.orders[fdata.get('ordering')]
            if isinstance(ob, dict):
                ob = dict(ob)
                o = ob.pop('_order')
                qs = qs.annotate(**ob).order_by(*get_deterministic_ordering(Voucher, o))
            elif isinstance(ob, (list, tuple)):
                qs = qs.order_by(*get_deterministic_ordering(Voucher, ob))
            else:
                qs = qs.order_by(*get_deterministic_ordering(Voucher, ob))

        return qs


class VoucherTagFilterForm(FilterForm):
    subevent = forms.ModelChoiceField(
        label=pgettext_lazy('subevent', 'Date'),
        queryset=SubEvent.objects.none(),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        elif 'subevent':
            del self.fields['subevent']

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('subevent'):
            qs = qs.filter(subevent_id=fdata.get('subevent').pk)

        return qs


class RefundFilterForm(FilterForm):
    orders = {'provider': 'provider', 'state': 'state', 'order': 'order__code',
              'source': 'source', 'amount': 'amount', 'created': 'created'}

    provider = forms.ChoiceField(
        label=_('Payment provider'),
        choices=[
            ('', _('All payment providers')),
        ],
        required=False,
    )
    status = forms.ChoiceField(
        label=_('Refund status'),
        choices=(
            ('', _('All open refunds')),
            ('all', _('All refunds')),
        ) + OrderRefund.REFUND_STATES,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['provider'].choices += [(k, v.verbose_name) for k, v
                                            in self.event.get_payment_providers().items()]

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        if fdata.get('provider'):
            qs = qs.filter(provider=fdata.get('provider'))

        if fdata.get('status'):
            if fdata.get('status') != 'all':
                qs = qs.filter(state=fdata.get('status'))
        else:
            qs = qs.filter(state__in=[OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_TRANSIT,
                                      OrderRefund.REFUND_STATE_EXTERNAL])

        if fdata.get('ordering'):
            qs = qs.order_by(*get_deterministic_ordering(OrderRefund, self.get_order_by()))
        return qs


class OverviewFilterForm(FilterForm):
    subevent = forms.ModelChoiceField(
        label=pgettext_lazy('subevent', 'Date'),
        queryset=SubEvent.objects.none(),
        required=False,
        empty_label=pgettext_lazy('subevent', 'All dates')
    )
    date_axis = forms.ChoiceField(
        label=_('Date filter'),
        choices=(
            ('', _('Filter by…')),
            ('order_date', _('Order date')),
            ('last_payment_date', _('Date of last successful payment')),
        ),
        required=False,
    )
    date_from = forms.DateField(
        label=_('Date from'),
        required=False,
        widget=DatePickerWidget,
    )
    date_until = forms.DateField(
        label=_('Date until'),
        required=False,
        widget=DatePickerWidget,
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
            self.fields['subevent'].widget = Select2(
                attrs={
                    'data-model-select2': 'event',
                    'data-select2-url': reverse('control:event.subevents.select2', kwargs={
                        'event': self.event.slug,
                        'organizer': self.event.organizer.slug,
                    }),
                    'data-placeholder': pgettext_lazy('subevent', 'All dates')
                }
            )
            self.fields['subevent'].widget.choices = self.fields['subevent'].choices
        elif 'subevent':
            del self.fields['subevent']


class CheckinFilterForm(FilterForm):
    status = forms.ChoiceField(
        label=_('Status'),
        choices=[
            ('', _('All check-ins')),
            ('successful', _('Successful check-ins')),
            ('unsuccessful', _('Unsuccessful check-ins')),
        ] + list(Checkin.REASONS),
        required=False
    )
    type = forms.ChoiceField(
        label=_('Scan type'),
        choices=[
            ('', _('All directions')),
        ] + list(Checkin.CHECKIN_TYPES),
        required=False
    )
    itemvar = forms.ChoiceField(
        label=_("Product"),
        required=False
    )
    device = SafeModelChoiceField(
        label=_('Device'),
        empty_label=_('All devices'),
        queryset=Device.objects.none(),
        required=False
    )
    gate = SafeModelChoiceField(
        label=_('Gate'),
        empty_label=_('All gates'),
        queryset=Gate.objects.none(),
        required=False
    )
    checkin_list = SafeModelChoiceField(queryset=CheckinList.objects.none(), required=False)  # overridden later
    datetime_from = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
        }),
        label=pgettext_lazy('filter', 'Start date'),
        required=False,
    )
    datetime_until = forms.SplitDateTimeField(
        widget=SplitDateTimePickerWidget(attrs={
        }),
        label=pgettext_lazy('filter', 'End date'),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        self.fields['device'].queryset = self.event.organizer.devices.all().order_by('device_id')
        self.fields['device'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:organizer.devices.select2', kwargs={
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('All devices'),
            }
        )
        self.fields['device'].widget.choices = self.fields['device'].choices
        self.fields['device'].label = _('Device')

        self.fields['gate'].queryset = self.event.organizer.gates.all()
        self.fields['gate'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:organizer.gates.select2', kwargs={
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('All gates'),
            }
        )
        self.fields['gate'].widget.choices = self.fields['gate'].choices
        self.fields['gate'].label = _('Gate')

        self.fields['checkin_list'].queryset = self.event.checkin_lists.all()
        self.fields['checkin_list'].widget = Select2(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.orders.checkinlists.select2', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('Check-in list'),
            }
        )
        self.fields['checkin_list'].widget.choices = self.fields['checkin_list'].choices
        self.fields['checkin_list'].label = _('Check-in list')

        choices = [('', _('All products'))]
        for i in self.event.items.prefetch_related('variations').all():
            variations = list(i.variations.all())
            if variations:
                choices.append((str(i.pk), _('{product} – Any variation').format(product=str(i))))
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (str(i), v.value)))
            else:
                choices.append((str(i.pk), str(i)))
        self.fields['itemvar'].choices = choices

        self.fields['itemvar'].choices = choices
        self.fields['itemvar'].widget = Select2ItemVarQuota(
            attrs={
                'data-model-select2': 'generic',
                'data-select2-url': reverse('control:event.items.itemvar.select2', kwargs={
                    'event': self.event.slug,
                    'organizer': self.event.organizer.slug,
                }),
                'data-placeholder': _('All products')
            }
        )
        self.fields['itemvar'].required = False
        self.fields['itemvar'].widget.choices = self.fields['itemvar'].choices

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('status'):
            s = fdata.get('status')
            if s == 'successful':
                qs = qs.filter(successful=True)
            elif s == 'unsuccessful':
                qs = qs.filter(successful=False)
            elif s:
                qs = qs.filter(successful=False, error_reason=s)

        if fdata.get('type'):
            qs = qs.filter(type=fdata.get('type'))

        if fdata.get('itemvar'):
            if '-' in fdata.get('itemvar'):
                qs = qs.alias(
                    item_id=Coalesce('raw_item_id', 'position__item_id'),
                    variation_id=Coalesce('raw_variation_id', 'position__variation_id'),
                ).filter(
                    item_id=fdata.get('itemvar').split('-')[0],
                    variation_id=fdata.get('itemvar').split('-')[1]
                )
            else:
                qs = qs.alias(
                    item_id=Coalesce('raw_item_id', 'position__item_id'),
                ).filter(item_id=fdata.get('itemvar'))

        if fdata.get('device'):
            qs = qs.filter(device_id=fdata.get('device').pk)

        if fdata.get('gate'):
            qs = qs.filter(gate_id=fdata.get('gate').pk)

        if fdata.get('checkin_list'):
            qs = qs.filter(list_id=fdata.get('checkin_list').pk)

        if fdata.get('datetime_from'):
            qs = qs.filter(datetime__gte=fdata.get('datetime_from'))

        if fdata.get('datetime_until'):
            qs = qs.filter(datetime__lte=fdata.get('datetime_until'))

        return qs


class DeviceFilterForm(FilterForm):
    orders = {
        'name': Upper('name'),
        '-name': Upper('name').desc(),
        'device_id': 'device_id',
        'initialized': F('initialized').asc(nulls_last=True),
        '-initialized': F('initialized').desc(nulls_first=True),
    }
    query = forms.CharField(
        label=_('Search query'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search query'),
            'autofocus': 'autofocus'
        }),
        required=False
    )
    gate = forms.ModelChoiceField(
        queryset=Gate.objects.none(),
        label=_('Gate'),
        empty_label=_('All gates'),
        required=False,
    )
    software_brand = forms.ChoiceField(
        label=_('Software'),
        choices=[
            ('', _('All')),
        ],
        required=False,
    )
    state = forms.ChoiceField(
        label=_('Device status'),
        choices=[
            ('all', _('All devices')),
            ('active', _('Active devices')),
            ('revoked', _('Revoked devices'))
        ],
        required=False
    )

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        self.fields['gate'].queryset = request.organizer.gates.all()
        self.fields['software_brand'].choices = [
            ('', _('All')),
        ] + [
            (f['software_brand'], f['software_brand']) for f in
            request.organizer.devices.order_by().values('software_brand').annotate(c=Count('*'))
            if f['software_brand']
        ]

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(name__icontains=query)
                | Q(unique_serial__icontains=query)
                | Q(hardware_brand__icontains=query)
                | Q(hardware_model__icontains=query)
                | Q(software_brand__icontains=query)
            )

        if fdata.get('gate'):
            qs = qs.filter(gate=fdata['gate'])

        if fdata.get('state') == 'active':
            qs = qs.filter(revoked=False)
        elif fdata.get('state') == 'revoked':
            qs = qs.filter(revoked=True)

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())
        else:
            qs = qs.order_by('-device_id')

        return qs
