import logging
from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import FormView, ListView

from pretix.base.i18n import LazyI18nString, language
from pretix.base.models import LogEntry, Order
from pretix.base.models.event import SubEvent
from pretix.base.templatetags.rich_text import markdown_compile_email
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.multidomain.urlreverse import build_absolute_uri
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
                    'recipients': logentry.parsed_data['recipients'],
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
        orders = qs.filter(statusq)
        orders = orders.filter(all_positions__item_id__in=[i.pk for i in form.cleaned_data.get('items')],
                               all_positions__canceled=False)
        if form.cleaned_data.get('subevent'):
            orders = orders.filter(all_positions__subevent__in=(form.cleaned_data.get('subevent'),),
                                   all_positions__canceled=False)
        orders = orders.distinct()

        self.output = {}
        if not orders:
            messages.error(self.request, _('There are no orders matching this selection.'))
            return self.get(self.request, *self.args, **self.kwargs)

        if self.request.POST.get("action") == "preview":
            for l in self.request.event.settings.locales:

                with language(l):

                    context_dict = {
                        'code': 'ORDER1234',
                        'event': self.request.event.name,
                        'date': date_format(now(), 'SHORT_DATE_FORMAT'),
                        'expire_date': date_format(now() + timedelta(days=7), 'SHORT_DATE_FORMAT'),
                        'url': build_absolute_uri(self.request.event, 'presale:event.order.open', kwargs={
                            'order': 'ORDER1234',
                            'secret': 'longrandomsecretabcdef123456',
                            'hash': 'abcdef',
                        }),
                        'invoice_name': _('John Doe'),
                        'invoice_company': _('Sample Company LLC')
                    }

                    subject = form.cleaned_data['subject'].localize(l)
                    preview_subject = subject.format_map(context_dict)
                    message = form.cleaned_data['message'].localize(l)
                    preview_text = markdown_compile_email(message.format_map(context_dict))

                    self.output[l] = {
                        'subject': _('Subject: {subject}').format(subject=preview_subject),
                        'html': preview_text,
                    }

            return self.get(self.request, *self.args, **self.kwargs)

        send_mails.apply_async(
            kwargs={
                'recipients': form.cleaned_data['recipients'],
                'event': self.request.event.pk,
                'user': self.request.user.pk,
                'subject': form.cleaned_data['subject'].data,
                'message': form.cleaned_data['message'].data,
                'orders': [o.pk for o in orders],
                'items': [i.pk for i in form.cleaned_data.get('items')]
            }
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
        status = dict(Order.STATUS_CHOICE)
        status['overdue'] = _('pending with payment overdue')
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
                itemcache[i['id']] for i in log.pdata.get('items', [])
            ]
            if log.pdata.get('subevent'):
                try:
                    log.pdata['subevent_obj'] = self.request.event.subevents.get(pk=log.pdata['subevent']['id'])
                except SubEvent.DoesNotExist:
                    pass

        return ctx
