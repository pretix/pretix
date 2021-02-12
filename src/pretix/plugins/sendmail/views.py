import logging

import bleach
import dateutil
from django.contrib import messages
from django.db.models import Exists, OuterRef, Q
from django.http import Http404
from django.shortcuts import redirect
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView

from pretix.base.email import get_available_placeholders
from pretix.base.i18n import LazyI18nString, language
from pretix.base.models import LogEntry, Order, OrderPosition
from pretix.base.models.event import SubEvent
from pretix.base.services.mail import TolerantDict
from pretix.base.templatetags.rich_text import markdown_compile_email
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.plugins.sendmail.tasks import send_mails

from . import forms

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
                ql.append(Q(checkins__list_id=None))
            if form.cleaned_data.get('checkin_lists'):
                ql.append(Q(
                    checkins__list_id__in=[i.pk for i in form.cleaned_data.get('checkin_lists', [])],
                ))
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

        self.output = {}
        if not orders:
            messages.error(self.request, _('There are no orders matching this selection.'))
            return self.get(self.request, *self.args, **self.kwargs)

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
                    message = form.cleaned_data['message'].localize(l)
                    preview_text = markdown_compile_email(message.format_map(context_dict))

                    self.output[l] = {
                        'subject': _('Subject: {subject}').format(subject=preview_subject),
                        'html': preview_text,
                    }

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
                                         'orders in the next minutes.') % len(orders))

        return redirect(
            'plugins:sendmail:send',
            event=self.request.event.slug,
            organizer=self.request.event.organizer.slug
        )

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx['output'] = getattr(self, 'output', None)
        return ctx


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
