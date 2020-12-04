from datetime import datetime, time
from decimal import Decimal
from urllib.parse import urlencode

from django import forms
from django.apps import apps
from django.conf import settings
from django.db.models import Exists, F, Model, OuterRef, Q, QuerySet
from django.db.models.functions import Coalesce, ExtractWeekDay
from django.urls import reverse, reverse_lazy
from django.utils.formats import date_format, localize
from django.utils.functional import cached_property
from django.utils.timezone import get_current_timezone, make_aware, now
from django.utils.translation import gettext, gettext_lazy as _, pgettext_lazy

from pretix.base.channels import get_all_sales_channels
from pretix.base.forms.widgets import (
    DatePickerWidget, SplitDateTimePickerWidget,
)
from pretix.base.models import (
    Checkin, Event, EventMetaProperty, EventMetaValue, Invoice, InvoiceAddress,
    Item, Order, OrderPayment, OrderPosition, OrderRefund, Organizer, Question,
    QuestionAnswer, SubEvent,
)
from pretix.base.signals import register_payment_providers
from pretix.control.forms.widgets import Select2
from pretix.control.signals import order_search_filter_q
from pretix.helpers.countries import CachedCountries
from pretix.helpers.database import FixedOrderBy, rolledback_transaction
from pretix.helpers.dicts import move_to_end
from pretix.helpers.i18n import i18ncomp

PAYMENT_PROVIDERS = []


def get_all_payment_providers():
    global PAYMENT_PROVIDERS

    if PAYMENT_PROVIDERS:
        return PAYMENT_PROVIDERS

    with rolledback_transaction():
        event = Event.objects.create(
            plugins=",".join([app.name for app in apps.get_app_configs()]),
            name="INTERNAL",
            date_from=now(),
            organizer=Organizer.objects.create(name="INTERNAL")
        )
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
                (Order.STATUS_PENDING, _('Pending')),
                (Order.STATUS_PENDING + Order.STATUS_PAID, _('Pending or paid')),
            )),
            (_('Cancellations'), (
                (Order.STATUS_CANCELED, _('Canceled')),
                ('cp', _('Canceled (or with paid fee)')),
                ('rc', _('Cancellation requested')),
            )),
            (_('Payment process'), (
                (Order.STATUS_EXPIRED, _('Expired')),
                (Order.STATUS_PENDING + Order.STATUS_EXPIRED, _('Pending or expired')),
                ('o', _('Pending (overdue)')),
                ('overpaid', _('Overpaid')),
                ('underpaid', _('Underpaid')),
                ('pendingpaid', _('Pending (but fully paid)')),
            )),
            (_('Approval process'), (
                ('na', _('Approved, payment pending')),
                ('pa', _('Approval pending')),
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

            matching_invoices = Invoice.objects.filter(
                Q(invoice_no__iexact=u)
                | Q(invoice_no__iexact=u.zfill(5))
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
                | Q(pk__in=matching_invoices)
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
                )
            elif s == 'pendingpaid':
                qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
                qs = qs.filter(
                    Q(status__in=(Order.STATUS_EXPIRED, Order.STATUS_PENDING)) & Q(pending_sum_t__lte=0)
                    & Q(require_approval=False)
                )
            elif s == 'underpaid':
                qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
                qs = qs.filter(
                    status=Order.STATUS_PAID,
                    pending_sum_t__gt=0
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
            qs = qs.order_by(self.get_order_by())

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
            elif q.type in (Question.TYPE_CHOICE, Question.TYPE_CHOICE_MULTIPLE):
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
    sales_channel = forms.ChoiceField(
        label=_('Sales channel'),
        required=False,
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
            qs = qs.filter(datetime__gte=fdata.get('created_to'))
        if fdata.get('comment'):
            qs = qs.filter(comment__icontains=fdata.get('comment'))
        if fdata.get('sales_channel'):
            qs = qs.filter(sales_channel=fdata.get('sales_channel'))
        if fdata.get('total'):
            qs = qs.filter(total=fdata.get('total'))
        if fdata.get('email_known_to_work') is not None:
            qs = qs.filter(email_known_to_work=fdata.get('email_known_to_work'))
        if fdata.get('locale'):
            qs = qs.filter(locale=fdata.get('locale'))
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
            organizer_id__in=self.request.user.teams.values_list('organizer', flat=True)
        )


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
    date = forms.DateField(
        label=_('Date'),
        required=False,
        widget=DatePickerWidget
    )
    weekday = forms.ChoiceField(
        label=_('Weekday'),
        choices=(
            ('', _('All days')),
            ('2', _('Monday')),
            ('3', _('Tuesday')),
            ('4', _('Wednesday')),
            ('5', _('Thursday')),
            ('6', _('Friday')),
            ('7', _('Saturday')),
            ('1', _('Sunday')),
        ),
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
        super().__init__(*args, **kwargs)
        self.fields['date'].widget = DatePickerWidget()

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
            qs = qs.annotate(wday=ExtractWeekDay('date_from')).filter(wday=fdata.get('weekday'))

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(name__icontains=i18ncomp(query)) | Q(location__icontains=query)
            )

        if fdata.get('date'):
            date_start = make_aware(datetime.combine(
                fdata.get('date'),
                time(hour=0, minute=0, second=0, microsecond=0)
            ), get_current_timezone())
            date_end = make_aware(datetime.combine(
                fdata.get('date'),
                time(hour=23, minute=59, second=59, microsecond=999999)
            ), get_current_timezone())
            qs = qs.filter(
                Q(date_to__isnull=True, date_from__gte=date_start, date_from__lte=date_end) |
                Q(date_to__isnull=False, date_from__lte=date_end, date_to__gte=date_start)
            )

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())
        else:
            qs = qs.order_by('-date_from')

        return qs


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
        label=_('Empty'),
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


class EventFilterForm(FilterForm):
    orders = {
        'slug': 'slug',
        'organizer': 'organizer__name',
        'date_from': 'order_from',
        'date_to': 'order_to',
        'live': 'live',
        'sum_tickets_paid': 'sum_tickets_paid'
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
            qs = qs.order_by(self.get_order_by())

        return qs

    @cached_property
    def meta_properties(self):
        if self.organizer:
            return self.organizer.meta_properties.all()
        else:
            # We ignore superuser permissions here. This is intentional – we do not want to show super
            # users a form with all meta properties ever assigned.
            return EventMetaProperty.objects.filter(
                organizer_id__in=self.request.user.teams.values_list('organizer', flat=True)
            )


class CheckInFilterForm(FilterForm):
    orders = {
        'code': ('order__code', 'item__name'),
        '-code': ('-order__code', '-item__name'),
        'email': ('order__email', 'item__name'),
        '-email': ('-order__email', '-item__name'),
        'status': (FixedOrderBy(F('last_entry'), nulls_first=True, descending=True), 'order__code'),
        '-status': (FixedOrderBy(F('last_entry'), nulls_last=True), '-order__code'),
        'timestamp': (FixedOrderBy(F('last_entry'), nulls_first=True), 'order__code'),
        '-timestamp': (FixedOrderBy(F('last_entry'), nulls_last=True, descending=True), '-order__code'),
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
            ('3', pgettext_lazy('checkin state', 'Checked in but left')),
            ('2', pgettext_lazy('checkin state', 'Present')),
            ('1', _('Checked in')),
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

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        self.list = kwargs.pop('list')
        super().__init__(*args, **kwargs)
        if self.list.all_products:
            self.fields['item'].queryset = self.event.items.all()
        else:
            self.fields['item'].queryset = self.list.limit_products.all()

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
                qs = qs.filter(last_entry__isnull=False).filter(
                    Q(last_exit__isnull=True) | Q(last_exit__lt=F('last_entry'))
                )
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
                qs = qs.annotate(**ob).order_by(o)
            elif isinstance(ob, (list, tuple)):
                qs = qs.order_by(*ob)
            else:
                qs = qs.order_by(ob)

        if fdata.get('item'):
            qs = qs.filter(item=fdata.get('item'))

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
                choices.append((str(i.pk), _('{product} – Any variation').format(product=i.name)))
                for v in variations:
                    choices.append(('%d-%d' % (i.pk, v.pk), '%s – %s' % (i.name, v.value)))
            else:
                choices.append((str(i.pk), i.name))
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
                qs = qs.annotate(**ob).order_by(o)
            elif isinstance(ob, (list, tuple)):
                qs = qs.order_by(*ob)
            else:
                qs = qs.order_by(ob)

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
