from django import forms
from django.apps import apps
from django.db.models import Exists, F, OuterRef, Q
from django.db.models.functions import Coalesce, Concat
from django.utils.timezone import now
from django.utils.translation import pgettext_lazy, ugettext_lazy as _

from pretix.base.models import Event, Invoice, Item, Order, Organizer, SubEvent
from pretix.base.signals import register_payment_providers
from pretix.control.utils.i18n import i18ncomp
from pretix.helpers.database import FixedOrderBy, rolledback_transaction

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
            ('p', _('Paid')),
            ('n', _('Pending')),
            ('o', _('Pending (overdue)')),
            ('e', _('Expired')),
            ('ne', _('Pending or expired')),
            ('c', _('Canceled')),
            ('r', _('Refunded')),
        ),
        required=False,
    )

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            u = fdata.get('query')

            if "-" in u:
                code = (Q(event__slug__icontains=u.split("-")[0])
                        & Q(code__icontains=Order.normalize_code(u.split("-")[1])))
            else:
                code = Q(code__icontains=Order.normalize_code(u))

            matching_invoice = Invoice.objects.filter(
                order=OuterRef('pk'),
            ).annotate(
                inr=Concat('prefix', 'invoice_no')
            ).filter(
                Q(invoice_no__iexact=u)
                | Q(invoice_no__iexact=u.zfill(5))
                | Q(inr=u)
            )

            qs = qs.annotate(has_inv=Exists(matching_invoice))
            qs = qs.filter(
                code
                | Q(email__icontains=u)
                | Q(positions__attendee_name__icontains=u)
                | Q(positions__attendee_email__icontains=u)
                | Q(invoice_address__name__icontains=u)
                | Q(invoice_address__company__icontains=u)
                | Q(has_inv=True)
            )

        if fdata.get('status'):
            s = fdata.get('status')
            if s == 'o':
                qs = qs.filter(status=Order.STATUS_PENDING, expires__lt=now().replace(hour=0, minute=0, second=0))
            elif s == 'ne':
                qs = qs.filter(status__in=[Order.STATUS_PENDING, Order.STATUS_EXPIRED])
            else:
                qs = qs.filter(status=s)

        if fdata.get('ordering'):
            qs = qs.order_by(self.get_order_by())

        if fdata.get('provider'):
            qs = qs.filter(payment_provider=fdata.get('provider'))

        return qs


class EventOrderFilterForm(OrderFilterForm):
    orders = {'code': 'code', 'email': 'email', 'total': 'total',
              'datetime': 'datetime', 'status': 'status', 'pcnt': 'pcnt'}

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

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = self.event.items.all()
        self.fields['provider'].choices += [(k, v.verbose_name) for k, v
                                            in self.event.get_payment_providers().items()]

        if self.event.has_subevents:
            self.fields['subevent'].queryset = self.event.subevents.all()
        elif 'subevent':
            del self.fields['subevent']

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        if fdata.get('item'):
            qs = qs.filter(positions__item=fdata.get('item'))

        if fdata.get('subevent'):
            qs = qs.filter(positions__subevent=fdata.get('subevent'))

        return qs


class OrderSearchFilterForm(OrderFilterForm):
    orders = {'code': 'code', 'email': 'email', 'total': 'total',
              'datetime': 'datetime', 'status': 'status', 'pcnt': 'pcnt',
              'event': 'event'}

    organizer = forms.ModelChoiceField(
        label=_('Organizer'),
        queryset=Organizer.objects.none(),
        required=False,
        empty_label=_('All organizers')
    )

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        if request.user.is_superuser:
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
    query = forms.CharField(
        label=_('Event name'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Event name'),
            'autofocus': 'autofocus'
        }),
        required=False
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
                Q(presale_end__isnull=True) | Q(presale_end__gte=now())
            )
        elif fdata.get('status') == 'inactive':
            qs = qs.filter(active=False)
        elif fdata.get('status') == 'future':
            qs = qs.filter(presale_start__gte=now())
        elif fdata.get('status') == 'past':
            qs = qs.filter(presale_end__lte=now())

        if fdata.get('query'):
            query = fdata.get('query')
            qs = qs.filter(
                Q(name__icontains=i18ncomp(query)) | Q(location__icontains=query)
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
        ),
        required=False
    )
    organizer = forms.ModelChoiceField(
        label=_('Organizer'),
        queryset=Organizer.objects.none(),
        required=False,
        empty_label=_('All organizers')
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
        if request.user.is_superuser:
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
                 'display_name': Coalesce('attendee_name', 'addon_to__attendee_name')},
        '-name': {'_order': F('display_name').desc(nulls_last=True),
                  'display_name': Coalesce('attendee_name', 'addon_to__attendee_name')},
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
                | Q(order__email__icontains=u)
                | Q(attendee_name__icontains=u)
                | Q(attendee_email__icontains=u)
                | Q(order__invoice_address__name__icontains=u)
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
