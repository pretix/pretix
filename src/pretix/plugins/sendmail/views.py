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
from django.contrib.humanize.templatetags.humanize import intcomma
from django.db import transaction
from django.db.models import Count, Exists, Max, Min, OuterRef, Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import get_template
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _, ngettext
from django.views.generic import DeleteView, FormView, ListView, TemplateView

from pretix.base.email import get_available_placeholders
from pretix.base.i18n import LazyI18nString, language
from pretix.base.models import Checkin, LogEntry, Order, OrderPosition
from pretix.base.models.event import SubEvent
from pretix.base.templatetags.rich_text import markdown_compile_email
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import CreateView, PaginationMixin, UpdateView
from pretix.plugins.sendmail.tasks import (
    send_mails_to_orders, send_mails_to_waitinglist,
)

from ...helpers.format import format_map
from . import forms
from .models import Rule, ScheduledMail

logger = logging.getLogger('pretix.plugins.sendmail')


class IndexView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/sendmail/index.html'
    permission = 'can_change_orders'

    def get_context_data(self, **kwargs):
        from .signals import sendmail_view_classes
        classes = []
        for recv, resp in sendmail_view_classes.send(self.request.event):
            if isinstance(resp, (list, tuple)):
                classes += resp
            else:
                classes.append(resp)
        return super().get_context_data(**kwargs, views=[
            {
                'title': cls.TITLE,
                'description': cls.DESCRIPTION,
                'url': cls.get_url(self.request.event)
            } for cls in classes
        ])


class BaseSenderView(EventPermissionRequiredMixin, FormView):
    # These parameters usually SHOULD NOT be overridden
    template_name = 'pretixplugins/sendmail/send_form.html'
    permission = 'can_change_orders'

    # These parameters MUST be overridden by subclasses
    form_fragment_name = None
    context_parameters = ['event']
    task = None

    # These parameters MUST be overriden by subclasses in a way that allows static access

    ACTION_TYPE = None
    TITLE = ""
    DESCRIPTION = ""

    # The following methods MUST be overridden by subclasses

    @staticmethod
    def get_url(self, event):
        """Returns the URL for this view for a given event."""
        raise NotImplementedError

    def get_object_queryset(self, form):
        """Returns a queryset of objects that will become recipients."""
        return Order.objects.none()

    def describe_match_size(self, cnt):
        """Returns a short human-readable description of the recipient set, such as '3 attendees'."""
        raise NotImplementedError

    @classmethod
    def show_history_meta_data(cls, logentry, _cache_store):
        """Returns an HTML component for the history view."""
        raise NotImplementedError

    # The following methods MAY be overridden by subclasses

    def initial_from_logentry(self, logentry):
        return {
            'message': LazyI18nString(logentry.parsed_data['message']),
            'subject': LazyI18nString(logentry.parsed_data['subject']),
        }

    def get_success_url(self):
        return self.request.get_full_path()

    def get_task_kwargs(self, form, objects):
        kwargs = {
            'event': self.request.event.pk,
            'user': self.request.user.pk,
            'subject': form.cleaned_data['subject'].data,
            'message': form.cleaned_data['message'].data,
            'objects': [o.pk for o in objects],
        }
        attachment = form.cleaned_data.get('attachment')
        if attachment is not None and attachment is not False:
            kwargs['attachments'] = [form.cleaned_data['attachment'].id]
        return kwargs

    # The following methods SHOULD NOT Be overridden by subclasses, but in some cases it may be necessary

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        kwargs['context_parameters'] = self.context_parameters
        if 'from_log' in self.request.GET:
            try:
                from_log_id = self.request.GET.get('from_log')
                logentry = LogEntry.objects.get(
                    id=from_log_id,
                    event=self.request.event,
                    action_type=self.ACTION_TYPE
                )
                kwargs['initial'] = {
                    **self.initial_from_logentry(logentry),
                }
            except LogEntry.DoesNotExist:
                raise Http404(_('You supplied an invalid log entry ID'))
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not send the email. See below for details.'))
        return super().form_invalid(form)

    def form_valid(self, form):
        objects = self.get_object_queryset(form)
        ocnt = objects.count()

        self.output = {}
        if not ocnt:
            messages.error(self.request, _('There are no matching recipients for your selection.'))
            self.request.POST = self.request.POST.copy()
            self.request.POST.pop("action", "")
            return self.get(self.request, *self.args, **self.kwargs)

        if self.request.POST.get("action") != "send":
            for l in self.request.event.settings.locales:
                with language(l, self.request.event.settings.region):
                    context_dict = {}
                    for k, v in get_available_placeholders(self.request.event, self.context_parameters).items():
                        context_dict[k] = '<span class="placeholder" title="{}">{}</span>'.format(
                            _('This value will be replaced based on dynamic parameters.'),
                            v.render_sample(self.request.event)
                        )

                    subject = bleach.clean(form.cleaned_data['subject'].localize(l), tags=[])
                    preview_subject = format_map(subject, context_dict)
                    message = form.cleaned_data['message'].localize(l)
                    preview_text = markdown_compile_email(format_map(message, context_dict))

                    self.output[l] = {
                        'subject': _('Subject: {subject}').format(subject=preview_subject),
                        'html': preview_text,
                        'attachment': form.cleaned_data.get('attachment')
                    }

            self.object_count = ocnt
            return self.get(self.request, *self.args, **self.kwargs)

        self.task.apply_async(
            kwargs=self.get_task_kwargs(form, objects)
        )
        self.request.event.log_action(
            self.ACTION_TYPE,
            user=self.request.user,
            data=dict(form.cleaned_data)
        )
        messages.success(self.request, _('Your message has been queued and will be sent to the contact addresses of %s '
                                         'in the next few minutes.') % self.describe_match_size(len(objects)))

        return redirect(self.get_success_url())

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx['output'] = getattr(self, 'output', None)
        ctx['match_size'] = self.describe_match_size(getattr(self, 'object_count', None))
        ctx['form_fragment_name'] = self.form_fragment_name
        ctx['is_preview'] = self.request.method == 'POST' and self.request.POST.get('action') == 'preview' and ctx['form'].is_valid()
        ctx['view_title'] = self.TITLE
        return ctx

    def get_form(self, form_class=None):
        f = super().get_form(form_class)
        if self.request.method == 'POST' and self.request.POST.get('action') == 'preview':
            if f.is_valid():
                for fname, field in f.fields.items():
                    field.widget.attrs['disabled'] = 'disabled'
        return f


class OrderSendView(BaseSenderView):
    form_class = forms.OrderMailForm
    form_fragment_name = "pretixplugins/sendmail/send_form_fragment_orders.html"
    context_parameters = ['event', 'order', 'position_or_address']
    task = send_mails_to_orders

    ACTION_TYPE = 'pretix.plugins.sendmail.sent'
    TITLE = _("Orders or attendees")
    DESCRIPTION = _("Send an email to every customer, or to every person a ticket has been "
                    "purchased for, or a combination of both.")

    @classmethod
    def show_history_meta_data(cls, logentry, _cache_store):
        if 'itemcache' not in _cache_store:
            _cache_store['itemcache'] = {
                i.pk: str(i) for i in logentry.event.items.all()
            }
        if 'checkin_list_cache' not in _cache_store:
            _cache_store['checkin_list_cache'] = {
                i.pk: str(i) for i in logentry.event.checkin_lists.all()
            }
        if 'status' not in _cache_store:
            status = dict(Order.STATUS_CHOICE)
            status['overdue'] = _('pending with payment overdue')
            status['valid_if_pending'] = _('payment pending but already confirmed')
            status['na'] = _('payment pending (except unapproved or already confirmed)')
            status['pa'] = _('approval pending')
            status['r'] = status['c']
            _cache_store['status'] = status

        tpl = get_template('pretixplugins/sendmail/history_fragment_orders.html')
        logentry.pdata['sendto'] = [
            _cache_store['status'][s] for s in logentry.pdata['sendto']
        ]
        logentry.pdata['items'] = [
            _cache_store['itemcache'].get(i['id'], '?') for i in logentry.pdata.get('items', [])
        ]
        logentry.pdata['checkin_lists'] = [
            _cache_store['checkin_list_cache'].get(i['id'], '?')
            for i in logentry.pdata.get('checkin_lists', []) if i['id'] in _cache_store['checkin_list_cache']
        ]
        if logentry.pdata.get('subevent'):
            try:
                logentry.pdata['subevent_obj'] = logentry.event.subevents.get(pk=logentry.pdata['subevent']['id'])
            except SubEvent.DoesNotExist:
                pass
        return tpl.render({
            'log': logentry,
        })

    @classmethod
    def get_url(cls, event):
        return reverse(
            'plugins:sendmail:send.orders',
            kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            }
        )

    def initial_from_logentry(self, logentry: LogEntry):
        initial = super().initial_from_logentry(logentry)
        if 'recipients' in logentry.parsed_data:
            initial['recipients'] = logentry.parsed_data.get('recipients', 'orders')
        if 'sendto' in logentry.parsed_data:
            initial['sendto'] = logentry.parsed_data.get('sendto')
        if 'items' in logentry.parsed_data:
            initial['items'] = self.request.event.items.filter(
                id__in=[a['id'] for a in logentry.parsed_data['items']]
            )
        elif logentry.parsed_data.get('item'):
            initial['items'] = self.request.event.items.filter(
                id=logentry.parsed_data['item']['id']
            )
        if 'checkin_lists' in logentry.parsed_data:
            initial['checkin_lists'] = self.request.event.checkin_lists.filter(
                id__in=[c['id'] for c in logentry.parsed_data['checkin_lists']]
            )
        initial['filter_checkins'] = logentry.parsed_data.get('filter_checkins', False)
        initial['not_checked_in'] = logentry.parsed_data.get('not_checked_in', False)
        if logentry.parsed_data.get('subevents_from'):
            initial['subevents_from'] = dateutil.parser.parse(logentry.parsed_data['subevents_from'])
        if logentry.parsed_data.get('subevents_to'):
            initial['subevents_to'] = dateutil.parser.parse(logentry.parsed_data['subevents_to'])
        if logentry.parsed_data.get('created_from'):
            initial['created_from'] = dateutil.parser.parse(logentry.parsed_data['created_from'])
        if logentry.parsed_data.get('created_to'):
            initial['created_to'] = dateutil.parser.parse(logentry.parsed_data['created_to'])
        if logentry.parsed_data.get('attach_tickets'):
            initial['attach_tickets'] = logentry.parsed_data['attach_tickets']
        if logentry.parsed_data.get('attach_ical'):
            initial['attach_ical'] = logentry.parsed_data['attach_ical']
        if logentry.parsed_data.get('subevent'):
            try:
                initial['subevent'] = self.request.event.subevents.get(
                    pk=logentry.parsed_data['subevent']['id']
                )
            except SubEvent.DoesNotExist:
                pass
        return initial

    def get_object_queryset(self, form):
        qs = Order.objects.filter(event=self.request.event)
        statusq = Q(status__in=form.cleaned_data['sendto'])
        if 'overdue' in form.cleaned_data['sendto']:
            statusq |= Q(status=Order.STATUS_PENDING, require_approval=False, valid_if_pending=False, expires__lt=now())
        if 'pa' in form.cleaned_data['sendto']:
            statusq |= Q(status=Order.STATUS_PENDING, require_approval=True)
        if 'na' in form.cleaned_data['sendto']:
            statusq |= Q(status=Order.STATUS_PENDING, require_approval=False, valid_if_pending=False)
        if 'valid_if_pending' in form.cleaned_data['sendto']:
            statusq |= Q(status=Order.STATUS_PENDING, require_approval=False, valid_if_pending=True)
        orders = qs.filter(statusq)

        opq = OrderPosition.objects.filter(
            Q(item_id__in=[i.pk for i in form.cleaned_data.get('items')]) | Q(Exists(
                OrderPosition.objects.filter(
                    addon_to_id=OuterRef('pk'),
                    item_id__in=[i.pk for i in form.cleaned_data.get('items')]
                )
            )),
            order__event=self.request.event,
            canceled=False,
        )

        if form.cleaned_data.get('filter_checkins'):
            ql = []

            if form.cleaned_data.get('not_checked_in'):
                opq = opq.alias(
                    any_checkins=Exists(
                        Checkin.all.filter(
                            Q(position_id=OuterRef('pk')) | Q(position__addon_to_id=OuterRef('pk')),
                            successful=True
                        )
                    )
                )
                ql.append(Q(any_checkins=False))
            if form.cleaned_data.get('checkin_lists'):
                opq = opq.alias(
                    matching_checkins=Exists(
                        Checkin.all.filter(
                            Q(position_id=OuterRef('pk')) | Q(position__addon_to_id=OuterRef('pk')),
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

        # pk__in turns out to be faster than Exists(subquery) in many cases since we often filter on a large subset
        # of orderpositions
        return orders.filter(pk__in=opq.values_list('order_id'))

    def describe_match_size(self, cnt):
        return ngettext(
            '%(number)s matching order',
            '%(number)s matching orders',
            cnt or 0,
        ) % {
            'number': intcomma(cnt or 0),
        }

    def get_task_kwargs(self, form, objects):
        kwargs = super().get_task_kwargs(form, objects)
        kwargs.update({
            'recipients': form.cleaned_data['recipients'],
            'items': [i.pk for i in form.cleaned_data.get('items')],
            'not_checked_in': form.cleaned_data.get('not_checked_in'),
            'checkin_lists': [i.pk for i in form.cleaned_data.get('checkin_lists')],
            'filter_checkins': form.cleaned_data.get('filter_checkins'),
            'attach_tickets': form.cleaned_data.get('attach_tickets'),
            'attach_ical': form.cleaned_data.get('attach_ical'),
        })
        return kwargs


class WaitinglistSendView(BaseSenderView):
    form_class = forms.WaitinglistMailForm
    form_fragment_name = "pretixplugins/sendmail/send_form_fragment_waitinglist.html"
    context_parameters = ['event', 'waiting_list_entry', 'event_or_subevent']
    task = send_mails_to_waitinglist

    ACTION_TYPE = 'pretix.plugins.sendmail.sent.waitinglist'
    TITLE = _("Waiting list")
    DESCRIPTION = _("Send an email to every person currently waiting to receive a voucher through the waiting "
                    "list feature.")

    @classmethod
    def show_history_meta_data(cls, logentry, _cache_store):
        if 'itemcache' not in _cache_store:
            _cache_store['itemcache'] = {
                i.pk: str(i) for i in logentry.event.items.all()
            }

        tpl = get_template('pretixplugins/sendmail/history_fragment_waitinglist.html')
        logentry.pdata['items'] = [
            _cache_store['itemcache'].get(i['id'], '?') for i in logentry.pdata.get('items', [])
        ]
        if logentry.pdata.get('subevent'):
            try:
                logentry.pdata['subevent_obj'] = logentry.event.subevents.get(pk=logentry.pdata['subevent']['id'])
            except SubEvent.DoesNotExist:
                pass
        return tpl.render({
            'log': logentry,
        })

    @classmethod
    def get_url(cls, event):
        return reverse(
            'plugins:sendmail:send.waitinglist',
            kwargs={
                'event': event.slug,
                'organizer': event.organizer.slug,
            }
        )

    def initial_from_logentry(self, logentry: LogEntry):
        initial = super().initial_from_logentry(logentry)
        if 'items' in logentry.parsed_data:
            initial['items'] = self.request.event.items.filter(
                id__in=[a['id'] for a in logentry.parsed_data['items']]
            )
        if logentry.parsed_data.get('subevents_from'):
            initial['subevents_from'] = dateutil.parser.parse(logentry.parsed_data['subevents_from'])
        if logentry.parsed_data.get('subevents_to'):
            initial['subevents_to'] = dateutil.parser.parse(logentry.parsed_data['subevents_to'])
        if logentry.parsed_data.get('subevent'):
            try:
                initial['subevent'] = self.request.event.subevents.get(
                    pk=logentry.parsed_data['subevent']['id']
                )
            except SubEvent.DoesNotExist:
                pass
        return initial

    def get_object_queryset(self, form):
        qs = self.request.event.waitinglistentries.filter(voucher__isnull=True)

        qs = qs.filter(item__in=[i.pk for i in form.cleaned_data.get('items')])
        if form.cleaned_data.get('subevent'):
            qs = qs.filter(subevent=form.cleaned_data.get('subevent'))
        if form.cleaned_data.get('subevents_from'):
            qs = qs.filter(subevent__date_from__gte=form.cleaned_data.get('subevents_from'))
        if form.cleaned_data.get('subevents_to'):
            qs = qs.filter(subevent__date_from__lt=form.cleaned_data.get('subevents_to'))

        return qs

    def describe_match_size(self, cnt):
        return ngettext(
            '%(number)s waiting list entry',
            '%(number)s waiting list entries',
            cnt or 0,
        ) % {
            'number': intcomma(cnt or 0),
        }


class EmailHistoryView(EventPermissionRequiredMixin, ListView):
    template_name = 'pretixplugins/sendmail/history.html'
    permission = 'can_change_orders'
    model = LogEntry
    context_object_name = 'logs'
    paginate_by = 5

    @cached_property
    def type_map(self):
        from .signals import sendmail_view_classes
        classes = []
        for recv, resp in sendmail_view_classes.send(self.request.event):
            if isinstance(resp, (list, tuple)):
                classes += resp
            else:
                classes.append(resp)
        return {
            cls.ACTION_TYPE: cls
            for cls in classes
        }

    def get_queryset(self):
        qs = LogEntry.objects.filter(
            event=self.request.event,
            action_type__in=self.type_map.keys(),
        ).select_related('event', 'user')
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        _cache = {}
        for log in ctx['logs']:
            log.pdata = log.parsed_data
            log.pdata['locales'] = {}
            for locale, msg in log.pdata['message'].items():
                log.pdata['locales'][locale] = {
                    'message': msg,
                    'subject': log.pdata['subject'][locale]
                }
            log.view = {
                'url': self.type_map[log.action_type].get_url(self.request.event),
                'title': self.type_map[log.action_type].TITLE,
                'rendered_data': self.type_map[log.action_type].show_history_meta_data(log, _cache)
            }

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
                    context_dict = {}
                    for k, v in get_available_placeholders(self.request.event, ['event', 'order',
                                                                                'position_or_address']).items():
                        context_dict[k] = '<span class="placeholder" title="{}">{}</span>'.format(
                            _('This value will be replaced based on dynamic parameters.'),
                            v.render_sample(self.request.event)
                        )

                    subject = bleach.clean(form.cleaned_data['subject'].localize(l), tags=[])
                    preview_subject = format_map(subject, context_dict)
                    template = form.cleaned_data['template'].localize(l)
                    preview_text = markdown_compile_email(format_map(template, context_dict))

                    self.output[l] = {
                        'subject': _('Subject: {subject}').format(subject=preview_subject),
                        'html': preview_text,
                    }

            return self.get(self.request, *self.args, **self.kwargs)

        messages.success(self.request, _('Your rule has been created.'))

        form.instance.event = self.request.event

        with transaction.atomic():
            self.object = form.save()
            form.instance.log_action('pretix.plugins.sendmail.rule.added', user=self.request.user,
                                     data=dict(form.cleaned_data))

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
        return get_object_or_404(
            Rule.objects.annotate(
                total_mails=Count('scheduledmail'),
                sent_mails=Count('scheduledmail', filter=Q(scheduledmail__state=ScheduledMail.STATE_COMPLETED)),
            ),
            event=self.request.event,
            id=self.kwargs['rule']
        )

    def get_success_url(self):
        return reverse('plugins:sendmail:rule.update', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'rule': self.object.pk,
        })

    @transaction.atomic()
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        form.instance.log_action('pretix.plugins.sendmail.rule.changed', user=self.request.user,
                                 data=dict(form.cleaned_data))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        o = {}

        for lang in self.request.event.settings.locales:
            with language(lang, self.request.event.settings.region):
                placeholders = {}
                for k, v in get_available_placeholders(self.request.event, ['event', 'order', 'position_or_address']).items():
                    placeholders[k] = '<span class="placeholder" title="{}">{}</span>'.format(
                        _('This value will be replaced based on dynamic parameters.'),
                        v.render_sample(self.request.event)
                    )

                subject = bleach.clean(self.object.subject.localize(lang), tags=[])
                preview_subject = format_map(subject, placeholders)
                template = self.object.template.localize(lang)
                preview_text = markdown_compile_email(format_map(template, placeholders))

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
        ).order_by('-send_date', 'subject', 'pk')


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


class ScheduleView(EventPermissionRequiredMixin, PaginationMixin, ListView):
    template_name = 'pretixplugins/sendmail/rule_inspect.html'
    model = ScheduledMail
    context_object_name = 'scheduled_mails'

    @cached_property
    def rule(self):
        return get_object_or_404(Rule, event=self.request.event, id=self.kwargs['rule'])

    def get_queryset(self):
        return self.rule.scheduledmail_set.select_related('subevent').order_by(
            '-computed_datetime', '-pk'
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['rule'] = self.rule
        return ctx
