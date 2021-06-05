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
# This file contains Apache-licensed contributions copyrighted by: Daniel, Flavia Bastos, FlaviaBastos, Sanket Dasgupta,
# Sohalt, Tobias Kunze, asv-hungvt, pajowu
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import logging

import bleach
import dateutil
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Exists, Max, Min, OuterRef, Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import DeleteView, FormView, ListView

from pretix.base.email import get_available_placeholders
from pretix.base.i18n import LazyI18nString, language
from pretix.base.models import Checkin, LogEntry, Order, OrderPosition
from pretix.base.models.event import SubEvent
from pretix.base.services.mail import TolerantDict
from pretix.base.templatetags.rich_text import markdown_compile_email
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import CreateView, PaginationMixin, UpdateView
from pretix.plugins.sendmail.tasks import send_mails

from . import forms
from .models import Rule, ScheduledMail

logger = logging.getLogger('pretix.plugins.sendmail')


class SenderView(EventPermissionRequiredMixin, FormView):
    template_name = 'pretixplugins/sendmail/send_form.html'
    permission = 'can_change_orders'
    form_class = forms.MailForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        if 'from_log' in self.request.GET:
            try:
                from_log_id = self.request.GET.get('from_log')
                logentry = LogEntry.objects.get(
                    id=from_log_id,
                    event=self.request.event,
                    action_type='pretix.plugins.sendmail.sent'
                )
                kwargs['initial'] = {
                    'recipients': logentry.parsed_data.get('recipients', 'orders'),
                    'message': LazyI18nString(logentry.parsed_data['message']),
                    'subject': LazyI18nString(logentry.parsed_data['subject']),
                    'sendto': logentry.parsed_data['sendto'],
                }
                if 'items' in logentry.parsed_data:
                    kwargs['initial']['items'] = self.request.event.items.filter(
                        id__in=[a['id'] for a in logentry.parsed_data['items']]
                    )
                elif logentry.parsed_data.get('item'):
                    kwargs['initial']['items'] = self.request.event.items.filter(
                        id=logentry.parsed_data['item']['id']
                    )
                if 'checkin_lists' in logentry.parsed_data:
                    kwargs['initial']['checkin_lists'] = self.request.event.checkin_lists.filter(
                        id__in=[c['id'] for c in logentry.parsed_data['checkin_lists']]
                    )
                kwargs['initial']['filter_checkins'] = logentry.parsed_data.get('filter_checkins', False)
                kwargs['initial']['not_checked_in'] = logentry.parsed_data.get('not_checked_in', False)
                if logentry.parsed_data.get('subevents_from'):
                    kwargs['initial']['subevents_from'] = dateutil.parser.parse(logentry.parsed_data['subevents_from'])
                if logentry.parsed_data.get('subevents_to'):
                    kwargs['initial']['subevents_to'] = dateutil.parser.parse(logentry.parsed_data['subevents_to'])
                if logentry.parsed_data.get('created_from'):
                    kwargs['initial']['created_from'] = dateutil.parser.parse(logentry.parsed_data['created_from'])
                if logentry.parsed_data.get('created_to'):
                    kwargs['initial']['created_to'] = dateutil.parser.parse(logentry.parsed_data['created_to'])
                if logentry.parsed_data.get('subevent'):
                    try:
                        kwargs['initial']['subevent'] = self.request.event.subevents.get(
                            pk=logentry.parsed_data['subevent']['id']
                        )
                    except SubEvent.DoesNotExist:
                        pass
            except LogEntry.DoesNotExist:
                raise Http404(_('You supplied an invalid log entry ID'))
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not send the email. See below for details.'))
        return super().form_invalid(form)

    def form_valid(self, form):
        qs = Order.objects.filter(event=self.request.event)
        statusq = Q(status__in=form.cleaned_data['sendto'])
        if 'overdue' in form.cleaned_data['sendto']:
            statusq |= Q(status=Order.STATUS_PENDING, expires__lt=now())
        if 'pa' in form.cleaned_data['sendto']:
            statusq |= Q(status=Order.STATUS_PENDING, require_approval=True)
        if 'na' in form.cleaned_data['sendto']:
            statusq |= Q(status=Order.STATUS_PENDING, require_approval=False)
        orders = qs.filter(statusq)

        opq = OrderPosition.objects.filter(
            order=OuterRef('pk'),
            canceled=False,
            item_id__in=[i.pk for i in form.cleaned_data.get('items')],
        )

        if form.cleaned_data.get('filter_checkins'):
            ql = []

            if form.cleaned_data.get('not_checked_in'):
                opq = opq.alias(
                    any_checkins=Exists(
                        Checkin.all.filter(
                            position_id=OuterRef('pk'),
                            successful=True
                        )
                    )
                )
                ql.append(Q(any_checkins=False))
            if form.cleaned_data.get('checkin_lists'):
                opq = opq.alias(
                    matching_checkins=Exists(
                        Checkin.all.filter(
                            position_id=OuterRef('pk'),
                            list_id__in=[i.pk for i in form.cleaned_data.get('checkin_lists', [])],
                            successful=True
                        )
                    )
                )
                ql.append(Q(matching_checkins=True))
            if len(ql) == 2:
                opq = opq.filter(ql[0] | ql[1])
            elif ql:
                opq = opq.filter(ql[0])
            else:
                opq = opq.none()

        if form.cleaned_data.get('subevent'):
            opq = opq.filter(subevent=form.cleaned_data.get('subevent'))
        if form.cleaned_data.get('subevents_from'):
            opq = opq.filter(subevent__date_from__gte=form.cleaned_data.get('subevents_from'))
        if form.cleaned_data.get('subevents_to'):
            opq = opq.filter(subevent__date_from__lt=form.cleaned_data.get('subevents_to'))
        if form.cleaned_data.get('created_from'):
            opq = opq.filter(order__datetime__gte=form.cleaned_data.get('created_from'))
        if form.cleaned_data.get('created_to'):
            opq = opq.filter(order__datetime__lt=form.cleaned_data.get('created_to'))

        orders = orders.annotate(match_pos=Exists(opq)).filter(match_pos=True).distinct()

        ocnt = orders.count()

        self.output = {}
        if not ocnt:
            messages.error(self.request, _('There are no orders matching this selection.'))
            return self.get(self.request, *self.args, **self.kwargs)

        if self.request.POST.get("action") != "send":
            for l in self.request.event.settings.locales:
                with language(l, self.request.event.settings.region):
                    context_dict = TolerantDict()
                    for k, v in get_available_placeholders(self.request.event, ['event', 'order',
                                                                                'position_or_address']).items():
                        context_dict[k] = '<span class="placeholder" title="{}">{}</span>'.format(
                            _('This value will be replaced based on dynamic parameters.'),
                            v.render_sample(self.request.event)
                        )

                    subject = bleach.clean(form.cleaned_data['subject'].localize(l), tags=[])
                    preview_subject = subject.format_map(context_dict)
                    message = form.cleaned_data['message'].localize(l)
                    preview_text = markdown_compile_email(message.format_map(context_dict))

                    self.output[l] = {
                        'subject': _('Subject: {subject}').format(subject=preview_subject),
                        'html': preview_text,
                        'attachment': form.cleaned_data.get('attachment')
                    }

            self.order_count = ocnt
            return self.get(self.request, *self.args, **self.kwargs)

        kwargs = {
            'recipients': form.cleaned_data['recipients'],
            'event': self.request.event.pk,
            'user': self.request.user.pk,
            'subject': form.cleaned_data['subject'].data,
            'message': form.cleaned_data['message'].data,
            'orders': [o.pk for o in orders],
            'items': [i.pk for i in form.cleaned_data.get('items')],
            'not_checked_in': form.cleaned_data.get('not_checked_in'),
            'checkin_lists': [i.pk for i in form.cleaned_data.get('checkin_lists')],
            'filter_checkins': form.cleaned_data.get('filter_checkins'),
        }
        if form.cleaned_data.get('attachment') is not None:
            kwargs['attachments'] = [form.cleaned_data['attachment'].id]

        send_mails.apply_async(
            kwargs=kwargs
        )
        self.request.event.log_action('pretix.plugins.sendmail.sent',
                                      user=self.request.user,
                                      data=dict(form.cleaned_data))
        messages.success(self.request, _('Your message has been queued and will be sent to the contact addresses of %d '
                                         'orders in the next few minutes.') % len(orders))

        return redirect(
            'plugins:sendmail:send',
            event=self.request.event.slug,
            organizer=self.request.event.organizer.slug
        )

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx['output'] = getattr(self, 'output', None)
        ctx['order_count'] = getattr(self, 'order_count', None)
        ctx['is_preview'] = self.request.method == 'POST' and self.request.POST.get('action') == 'preview'
        return ctx

    def get_form(self, form_class=None):
        f = super().get_form(form_class)
        if self.request.method == 'POST' and self.request.POST.get('action') == 'preview':
            for fname, field in f.fields.items():
                field.widget.attrs['disabled'] = 'disabled'
        return f


class EmailHistoryView(EventPermissionRequiredMixin, ListView):
    template_name = 'pretixplugins/sendmail/history.html'
    permission = 'can_change_orders'
    model = LogEntry
    context_object_name = 'logs'
    paginate_by = 5

    def get_queryset(self):
        qs = LogEntry.objects.filter(
            event=self.request.event,
            action_type='pretix.plugins.sendmail.sent'
        ).select_related('event', 'user')
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        itemcache = {
            i.pk: str(i) for i in self.request.event.items.all()
        }
        checkin_list_cache = {
            i.pk: str(i) for i in self.request.event.checkin_lists.all()
        }
        status = dict(Order.STATUS_CHOICE)
        status['overdue'] = _('pending with payment overdue')
        status['na'] = _('payment pending (except unapproved)')
        status['pa'] = _('approval pending')
        status['r'] = status['c']
        for log in ctx['logs']:
            log.pdata = log.parsed_data
            log.pdata['locales'] = {}
            for locale, msg in log.pdata['message'].items():
                log.pdata['locales'][locale] = {
                    'message': msg,
                    'subject': log.pdata['subject'][locale]
                }
            log.pdata['sendto'] = [
                status[s] for s in log.pdata['sendto']
            ]
            log.pdata['items'] = [
                itemcache.get(i['id'], '?') for i in log.pdata.get('items', [])
            ]
            log.pdata['checkin_lists'] = [
                checkin_list_cache.get(i['id'], '?')
                for i in log.pdata.get('checkin_lists', []) if i['id'] in checkin_list_cache
            ]
            if log.pdata.get('subevent'):
                try:
                    log.pdata['subevent_obj'] = self.request.event.subevents.get(pk=log.pdata['subevent']['id'])
                except SubEvent.DoesNotExist:
                    pass

        return ctx


class CreateRule(EventPermissionRequiredMixin, CreateView):
    template_name = 'pretixplugins/sendmail/rule_create.html'
    permission = 'can_change_event_settings'
    form_class = forms.RuleForm

    model = Rule

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def form_valid(self, form):
        self.output = {}

        if self.request.POST.get("action") == "preview":
            for l in self.request.event.settings.locales:
                with language(l, self.request.event.settings.region):
                    context_dict = TolerantDict()
                    for k, v in get_available_placeholders(self.request.event, ['event', 'order',
                                                                                'position_or_address']).items():
                        context_dict[k] = '<span class="placeholder" title="{}">{}</span>'.format(
                            _('This value will be replaced based on dynamic parameters.'),
                            v.render_sample(self.request.event)
                        )

                    subject = bleach.clean(form.cleaned_data['subject'].localize(l), tags=[])
                    preview_subject = subject.format_map(context_dict)
                    template = form.cleaned_data['template'].localize(l)
                    preview_text = markdown_compile_email(template.format_map(context_dict))

                    self.output[l] = {
                        'subject': _('Subject: {subject}').format(subject=preview_subject),
                        'html': preview_text,
                    }

            return self.get(self.request, *self.args, **self.kwargs)

        messages.success(self.request, _('Your rule has been created.'))

        form.instance.event = self.request.event

        self.object = form.save()

        return redirect(
            'plugins:sendmail:rule.update',
            event=self.request.event.slug,
            organizer=self.request.event.organizer.slug,
            rule=self.object.pk,
        )


class UpdateRule(EventPermissionRequiredMixin, UpdateView):
    model = Rule
    form_class = forms.RuleForm
    template_name = 'pretixplugins/sendmail/rule_update.html'
    permission = 'can_change_event_settings'

    def get_object(self, queryset=None) -> Rule:
        return get_object_or_404(Rule, event=self.request.event, id=self.kwargs['rule'])

    def get_success_url(self):
        return reverse('plugins:sendmail:rule.update', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'rule': self.object.pk,
        })

    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        o = {}

        for lang in self.request.event.settings.locales:
            with language(lang, self.request.event.settings.region):
                placeholders = TolerantDict()
                for k, v in get_available_placeholders(self.request.event, ['event', 'order', 'position_or_address']).items():
                    placeholders[k] = '<span class="placeholder" title="{}">{}</span>'.format(
                        _('This value will be replaced based on dynamic parameters.'),
                        v.render_sample(self.request.event)
                    )

                subject = bleach.clean(self.object.subject.localize(lang), tags=[])
                preview_subject = subject.format_map(placeholders)
                template = self.object.template.localize(lang)
                preview_text = markdown_compile_email(template.format_map(placeholders))

                o[lang] = {
                    'subject': _('Subject: {subject}'.format(subject=preview_subject)),
                    'html': preview_text,
                }

        ctx['output'] = o

        return ctx


class ListRules(EventPermissionRequiredMixin, PaginationMixin, ListView):
    template_name = 'pretixplugins/sendmail/rule_list.html'
    model = Rule
    context_object_name = 'rules'

    def get_queryset(self):
        return self.request.event.sendmail_rules.annotate(
            total_mails=Count('scheduledmail'),
            sent_mails=Count('scheduledmail', filter=Q(scheduledmail__state=ScheduledMail.STATE_COMPLETED)),
            last_execution=Max(
                'scheduledmail__computed_datetime',
                filter=Q(scheduledmail__state=ScheduledMail.STATE_COMPLETED)
            ),
            next_execution=Min(
                'scheduledmail__computed_datetime',
                filter=Q(scheduledmail__state=ScheduledMail.STATE_SCHEDULED)
            ),
        ).prefetch_related(
            'limit_products'
        )


class DeleteRule(EventPermissionRequiredMixin, DeleteView):
    model = Rule
    permission = 'can_change_event_settings'
    template_name = 'pretixplugins/sendmail/rule_delete.html'
    context_object_name = 'rule'

    def get_success_url(self):
        return reverse("plugins:sendmail:rule.list", kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_object(self, queryset=None) -> Rule:
        return get_object_or_404(Rule, event=self.request.event, id=self.kwargs['rule'])

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        self.request.event.log_action('pretix.plugins.sendmail.rule.deleted',
                                      user=self.request.user,
                                      data={
                                          'subject': self.object.subject,
                                          'text': self.object.template,
                                      })

        self.object.delete()
        messages.success(self.request, _('The selected rule has been deleted.'))
        return HttpResponseRedirect(success_url)
