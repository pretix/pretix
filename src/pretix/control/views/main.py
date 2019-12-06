from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import (
    F, IntegerField, Max, Min, OuterRef, Prefetch, Subquery, Sum,
)
from django.db.models.functions import Coalesce, Greatest
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.utils.translation import ugettext, ugettext_lazy as _
from django.views import View
from django.views.generic import ListView
from i18nfield.strings import LazyI18nString

from pretix.base.forms import SafeSessionWizardView
from pretix.base.i18n import language
from pretix.base.models import Event, EventMetaValue, Organizer, Quota, Team
from pretix.control.forms.event import (
    EventWizardBasicsForm, EventWizardCopyForm, EventWizardFoundationForm,
)
from pretix.control.forms.filter import EventFilterForm
from pretix.control.permissions import OrganizerPermissionRequiredMixin
from pretix.control.views import PaginationMixin


class EventList(PaginationMixin, ListView):
    model = Event
    context_object_name = 'events'
    template_name = 'pretixcontrol/events/index.html'

    def get_queryset(self):
        qs = self.request.user.get_events_with_any_permission(self.request).prefetch_related(
            'organizer', '_settings_objects', 'organizer___settings_objects', 'organizer__meta_properties',
            Prefetch(
                'meta_values',
                EventMetaValue.objects.select_related('property'),
                to_attr='meta_values_cached'
            )
        ).order_by('-date_from')

        qs = qs.annotate(
            min_from=Min('subevents__date_from'),
            max_from=Max('subevents__date_from'),
            max_to=Max('subevents__date_to'),
            max_fromto=Greatest(Max('subevents__date_to'), Max('subevents__date_from'))
        ).annotate(
            order_from=Coalesce('min_from', 'date_from'),
            order_to=Coalesce('max_fromto', 'max_to', 'max_from', 'date_to', 'date_from'),
        )

        sum_tickets_paid = Quota.objects.filter(
            event=OuterRef('pk'), subevent__isnull=True
        ).order_by().values('event').annotate(
            s=Sum('cached_availability_paid_orders')
        ).values(
            's'
        )

        qs = qs.annotate(
            sum_tickets_paid=Subquery(sum_tickets_paid, output_field=IntegerField())
        ).prefetch_related(
            Prefetch('quotas',
                     queryset=Quota.objects.filter(subevent__isnull=True).annotate(s=Coalesce(F('size'), 0)).order_by('-s'),
                     to_attr='first_quotas')
        )

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        orga_c = Organizer.objects.filter(
            pk__in=self.request.user.teams.values_list('organizer', flat=True)
        ).count()
        ctx['hide_orga'] = orga_c <= 1
        ctx['meta_fields'] = [
            self.filter_form[k] for k in self.filter_form.fields if k.startswith('meta_')
        ]

        for s in ctx['events']:
            s.first_quotas = s.first_quotas[:4]
            for q in s.first_quotas:
                q.cached_avail = (
                    (q.cached_availability_state, q.cached_availability_number)
                    if q.cached_availability_time is not None
                    else q.availability(allow_cache=True)
                )
                if q.size is not None:
                    q.percent_paid = min(
                        100,
                        round(q.cached_availability_paid_orders / q.size * 100) if q.size > 0 else 100
                    )
        return ctx

    @cached_property
    def filter_form(self):
        return EventFilterForm(data=self.request.GET, request=self.request)


def condition_copy(wizard):
    return (
        not wizard.clone_from and
        EventWizardCopyForm.copy_from_queryset(wizard.request.user, wizard.request.session).exists()
    )


class EventWizard(SafeSessionWizardView):
    form_list = [
        ('foundation', EventWizardFoundationForm),
        ('basics', EventWizardBasicsForm),
        ('copy', EventWizardCopyForm),
    ]
    templates = {
        'foundation': 'pretixcontrol/events/create_foundation.html',
        'basics': 'pretixcontrol/events/create_basics.html',
        'copy': 'pretixcontrol/events/create_copy.html',
    }
    condition_dict = {
        'copy': condition_copy
    }

    def get_form_initial(self, step):
        initial = super().get_form_initial(step)
        if self.clone_from:
            if step == 'foundation':
                initial['organizer'] = self.clone_from.organizer
                initial['locales'] = self.clone_from.settings.locales
                initial['has_subevents'] = self.clone_from.has_subevents
            elif step == 'basics':
                initial['name'] = self.clone_from.name
                initial['slug'] = self.clone_from.slug + '-2'
                initial['currency'] = self.clone_from.currency
                initial['date_from'] = self.clone_from.date_from
                initial['date_to'] = self.clone_from.date_to
                initial['geo_lat'] = self.clone_from.geo_lat
                initial['geo_lon'] = self.clone_from.geo_lon
                initial['presale_start'] = self.clone_from.presale_start
                initial['presale_end'] = self.clone_from.presale_end
                initial['location'] = self.clone_from.location
                initial['timezone'] = self.clone_from.settings.timezone
                initial['locale'] = self.clone_from.settings.locale
                if self.clone_from.settings.tax_rate_default:
                    initial['tax_rate'] = self.clone_from.settings.tax_rate_default.rate
        if 'organizer' in self.request.GET:
            if step == 'foundation':
                try:
                    qs = Organizer.objects.all()
                    if not self.request.user.has_active_staff_session(self.request.session.session_key):
                        qs = qs.filter(
                            id__in=self.request.user.teams.filter(can_create_events=True).values_list('organizer', flat=True)
                        )
                    initial['organizer'] = qs.get(slug=self.request.GET.get('organizer'))
                except Organizer.DoesNotExist:
                    pass

        return initial

    def dispatch(self, request, *args, **kwargs):
        self.clone_from = None
        if 'clone' in self.request.GET:
            try:
                clone_from = Event.objects.select_related('organizer').get(pk=self.request.GET.get("clone"))
            except Event.DoesNotExist:
                allow = False
            else:
                allow = (
                    request.user.has_event_permission(clone_from.organizer, clone_from,
                                                      'can_change_event_settings', request)
                    and request.user.has_event_permission(clone_from.organizer, clone_from,
                                                          'can_change_items', request)
                )
            if not allow:
                messages.error(self.request, _('You do not have permission to clone this event.'))
            else:
                self.clone_from = clone_from
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        ctx = super().get_context_data(form, **kwargs)
        ctx['has_organizer'] = self.request.user.teams.filter(can_create_events=True).exists()
        if self.steps.current == 'basics':
            ctx['organizer'] = self.get_cleaned_data_for_step('foundation').get('organizer')
        return ctx

    def render(self, form=None, **kwargs):
        if self.steps.current != 'foundation':
            fdata = self.get_cleaned_data_for_step('foundation')
            if fdata is None:
                return self.render_goto_step('foundation')

        return super().render(form, **kwargs)

    def get_form_kwargs(self, step=None):
        kwargs = {
            'user': self.request.user,
            'session': self.request.session,
        }
        if step != 'foundation':
            fdata = self.get_cleaned_data_for_step('foundation')
            if fdata is None:
                fdata = {
                    'organizer': Organizer(slug='_nonexisting'),
                    'has_subevents': False,
                    'locales': ['en']
                }
                # The show must go on, we catch this error in render()
            kwargs.update(fdata)
        return kwargs

    def get_template_names(self):
        return [self.templates[self.steps.current]]

    def done(self, form_list, form_dict, **kwargs):
        foundation_data = self.get_cleaned_data_for_step('foundation')
        basics_data = self.get_cleaned_data_for_step('basics')
        copy_data = self.get_cleaned_data_for_step('copy')

        with transaction.atomic(), language(basics_data['locale']):
            event = form_dict['basics'].instance
            event.organizer = foundation_data['organizer']
            event.plugins = settings.PRETIX_PLUGINS_DEFAULT
            event.has_subevents = foundation_data['has_subevents']
            event.testmode = True
            form_dict['basics'].save()

            if not EventWizardBasicsForm.has_control_rights(self.request.user, event.organizer):
                if basics_data["team"] is not None:
                    t = basics_data["team"]
                    t.limit_events.add(event)
                elif event.organizer.settings.event_team_provisioning:
                    t = Team.objects.create(
                        organizer=event.organizer, name=_('Team {event}').format(event=event.name),
                        can_change_event_settings=True, can_change_items=True,
                        can_view_orders=True, can_change_orders=True, can_view_vouchers=True,
                        can_change_vouchers=True
                    )
                    t.members.add(self.request.user)
                    t.limit_events.add(event)

            if event.has_subevents:
                se = event.subevents.create(
                    name=event.name,
                    date_from=event.date_from,
                    date_to=event.date_to,
                    presale_start=event.presale_start,
                    presale_end=event.presale_end,
                    location=event.location,
                    geo_lat=event.geo_lat,
                    geo_lon=event.geo_lon,
                    active=True
                )

            logdata = {}
            for f in form_list:
                logdata.update({
                    k: v for k, v in f.cleaned_data.items()
                })
            event.log_action('pretix.event.settings', user=self.request.user, data=logdata)

            if copy_data and copy_data['copy_from_event']:
                from_event = copy_data['copy_from_event']
                event.copy_data_from(from_event)
            elif self.clone_from:
                event.copy_data_from(self.clone_from)
            else:
                if event.has_subevents:
                    event.checkin_lists.create(
                        name=str(se),
                        all_products=True,
                        subevent=se
                    )
                else:
                    self.checkin_lists.create(
                        name=_('Default'),
                        all_products=True
                    )
                event.set_defaults()

            if basics_data['tax_rate']:
                if not event.settings.tax_rate_default or event.settings.tax_rate_default.rate != basics_data['tax_rate']:
                    event.settings.tax_rate_default = event.tax_rules.create(
                        name=LazyI18nString.from_gettext(ugettext('VAT')),
                        rate=basics_data['tax_rate']
                    )

            event.settings.set('timezone', basics_data['timezone'])
            event.settings.set('locale', basics_data['locale'])
            event.settings.set('locales', foundation_data['locales'])

        if (copy_data and copy_data['copy_from_event']) or self.clone_from or event.has_subevents:
            return redirect(reverse('control:event.settings', kwargs={
                'organizer': event.organizer.slug,
                'event': event.slug,
            }) + '?congratulations=1')
        else:
            return redirect(reverse('control:event.quick', kwargs={
                'organizer': event.organizer.slug,
                'event': event.slug,
            }) + '?congratulations=1')


class SlugRNG(OrganizerPermissionRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        # See Order.assign_code
        charset = list('abcdefghjklmnpqrstuvwxyz3789')
        for i in range(100):
            val = get_random_string(length=settings.ENTROPY['order_code'], allowed_chars=charset)
            if not self.request.organizer.events.filter(slug__iexact=val).exists():
                break

        return JsonResponse({'slug': val})
