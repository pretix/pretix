from datetime import datetime, time

from django import forms
from django.apps import apps
from django.db.models import Exists, F, OuterRef, Q
from django.db.models.functions import Coalesce, ExtractWeekDay
from django.urls import reverse, reverse_lazy
from django.utils.timezone import get_current_timezone, make_aware, now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _

from pretix.base.forms.widgets import DatePickerWidget
from pretix.base.models import (
    Checkin, Event, Invoice, Item, Order, OrderPayment, OrderPosition,
    OrderRefund, Organizer, Question, QuestionAnswer, SubEvent,
)
from pretix.base.signals import register_payment_providers
from pretix.control.forms.widgets import Select2
from pretix.helpers.database import FixedOrderBy, rolledback_transaction
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
        if o.startswith('-'):
            return '-' + self.orders[o[1:]]
        else:
            return self.orders[o]


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
            (Order.STATUS_PAID, _('Paid (or canceled with paid fee)')),
            (Order.STATUS_PENDING, _('Pending')),
            ('o', _('Pending (overdue)')),
            (Order.STATUS_PENDING + Order.STATUS_PAID, _('Pending or paid')),
            (Order.STATUS_EXPIRED, _('Expired')),
            (Order.STATUS_PENDING + Order.STATUS_EXPIRED, _('Pending or expired')),
            (Order.STATUS_CANCELED, _('Canceled')),
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
                Q(order=OuterRef('pk')) & Q(
                    Q(attendee_name_cached__icontains=u) | Q(attendee_email__icontains=u)
                    | Q(secret__istartswith=u)
                )
            ).values('id')

            qs = qs.annotate(has_pos=Exists(matching_positions)).filter(
                code
                | Q(email__icontains=u)
                | Q(invoice_address__name_cached__icontains=u)
                | Q(invoice_address__company__icontains=u)
                | Q(pk__in=matching_invoices)
                | Q(comment__icontains=u)
                | Q(has_pos=True)
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
    question = forms.ModelChoiceField(
        queryset=Question.objects.none(),
        required=False,
    )
    answer = forms.CharField(
        required=False
    )
    status = forms.ChoiceField(
        label=_('Order status'),
        choices=(
            ('', _('All orders')),
            (Order.STATUS_PAID, _('Paid (or canceled with paid fee)')),
            (Order.STATUS_PENDING, _('Pending')),
            ('o', _('Pending (overdue)')),
            (Order.STATUS_PENDING + Order.STATUS_PAID, _('Pending or paid')),
            (Order.STATUS_EXPIRED, _('Expired')),
            (Order.STATUS_PENDING + Order.STATUS_EXPIRED, _('Pending or expired')),
            (Order.STATUS_CANCELED, _('Canceled')),
            ('pa', _('Approval pending')),
            ('overpaid', _('Overpaid')),
            ('underpaid', _('Underpaid')),
            ('pendingpaid', _('Pending (but fully paid)'))
        ),
        required=False,
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

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        if fdata.get('item'):
            qs = qs.filter(all_positions__item=fdata.get('item'), all_positions__canceled=False).distinct()

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
                    answer__iexact=fdata.get('answer')
                )
                qs = qs.annotate(has_answer=Exists(answers)).filter(has_answer=True)

        if fdata.get('status') == 'overpaid':
            qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
            qs = qs.filter(
                Q(~Q(status=Order.STATUS_CANCELED) & Q(pending_sum_t__lt=0))
                | Q(Q(status=Order.STATUS_CANCELED) & Q(pending_sum_rc__lt=0))
            )
        elif fdata.get('status') == 'pendingpaid':
            qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
            qs = qs.filter(
                Q(status__in=(Order.STATUS_EXPIRED, Order.STATUS_PENDING)) & Q(pending_sum_t__lte=0)
                & Q(require_approval=False)
            )
        elif fdata.get('status') == 'underpaid':
            qs = Order.annotate_overpayments(qs, refunds=False, results=False, sums=True)
            qs = qs.filter(
                status=Order.STATUS_PAID,
                pending_sum_t__gt=0
            )
        elif fdata.get('status') == 'pa':
            qs = qs.filter(
                status=Order.STATUS_PENDING,
                require_approval=True
            )

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
        request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        if request.user.has_active_staff_session(request.session.session_key):
            self.fields['organizer'].queryset = Organizer.objects.all()
        else:
            self.fields['organizer'].queryset = Organizer.objects.filter(
                pk__in=request.user.teams.values_list('organizer', flat=True)
            )
        self.fields['provider'].choices += get_all_payment_providers()

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        if fdata.get('organizer'):
            qs = qs.filter(event__organizer=fdata.get('organizer'))

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
                Q(presale_end__isnull=True) | Q(presale_end__gte=now())
            )
        elif fdata.get('status') == 'inactive':
            qs = qs.filter(active=False)
        elif fdata.get('status') == 'future':
            qs = qs.filter(presale_start__gte=now())
        elif fdata.get('status') == 'past':
            qs = qs.filter(presale_end__lte=now())

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
        request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        if request.user.has_active_staff_session(request.session.session_key):
            self.fields['organizer'].queryset = Organizer.objects.all()
        else:
            self.fields['organizer'].queryset = Organizer.objects.filter(
                pk__in=request.user.teams.values_list('organizer', flat=True)
            )

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('status') == 'live':
            qs = qs.filter(live=True)
        elif fdata.get('status') == 'running':
            qs = qs.filter(
                live=True
            ).filter(
                Q(presale_start__isnull=True) | Q(presale_start__lte=now())
            ).filter(
                Q(presale_end__isnull=True) | Q(presale_end__gte=now())
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

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())

        return qs


class CheckInFilterForm(FilterForm):
    orders = {
        'code': ('order__code', 'item__name'),
        '-code': ('-order__code', '-item__name'),
        'email': ('order__email', 'item__name'),
        '-email': ('-order__email', '-item__name'),
        'status': (FixedOrderBy(F('last_checked_in'), nulls_first=True, descending=True), 'order__code'),
        '-status': (FixedOrderBy(F('last_checked_in'), nulls_last=True), '-order__code'),
        'timestamp': (FixedOrderBy(F('last_checked_in'), nulls_first=True), 'order__code'),
        '-timestamp': (FixedOrderBy(F('last_checked_in'), nulls_last=True, descending=True), '-order__code'),
        'item': ('item__name', 'variation__value', 'order__code'),
        '-item': ('-item__name', '-variation__value', '-order__code'),
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
                qs = qs.filter(last_checked_in__isnull=False)
            elif s == '0':
                qs = qs.filter(last_checked_in__isnull=True)

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
            qs = qs.order_by(self.get_order_by())

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
