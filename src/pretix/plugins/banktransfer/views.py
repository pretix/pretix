import csv
import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext as _
from django.views.generic import DetailView, ListView, View

from pretix.base.models import Order, OrderPayment, Quota
from pretix.base.services.mail import SendMailException
from pretix.base.settings import SettingsSandbox
from pretix.base.templatetags.money import money_filter
from pretix.control.permissions import (
    EventPermissionRequiredMixin, OrganizerPermissionRequiredMixin,
)
from pretix.control.views.organizer import OrganizerDetailViewMixin
from pretix.plugins.banktransfer import csvimport, mt940import
from pretix.plugins.banktransfer.models import BankImportJob, BankTransaction
from pretix.plugins.banktransfer.tasks import process_banktransfers, get_prefix_event_map

logger = logging.getLogger('pretix.plugins.banktransfer')


class ActionView(View):
    permission = 'can_change_orders'

    def _discard(self, trans):
        trans.state = BankTransaction.STATE_DISCARDED
        trans.shred_private_data()
        trans.save()
        return JsonResponse({
            'status': 'ok'
        })

    def _retry(self, trans):
        return self._accept_ignore_amount(trans)

    def _accept_ignore_amount(self, trans):
        if trans.order.status == Order.STATUS_PAID:
            return JsonResponse({
                'status': 'error',
                'message': _('The order is already marked as paid.')
            })
        elif trans.order.status == Order.STATUS_CANCELED:
            return JsonResponse({
                'status': 'error',
                'message': _('The order has already been canceled.')
            })

        p = trans.order.payments.get_or_create(
            amount=trans.amount,
            provider='banktransfer',
            state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
            defaults={
                'state': OrderPayment.PAYMENT_STATE_CREATED,
            }
        )[0]
        p.info_data = {
            'reference': trans.reference,
            'date': trans.date,
            'payer': trans.payer,
            'trans_id': trans.pk
        }
        try:
            p.confirm(user=self.request.user)
        except Quota.QuotaExceededException as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })
        except SendMailException:
            return JsonResponse({
                'status': 'error',
                'message': _('Problem sending email.')
            })
        else:
            trans.state = BankTransaction.STATE_VALID
            trans.save()
            trans.order.payments.filter(
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
            ).update(state=OrderPayment.PAYMENT_STATE_CANCELED)
            return JsonResponse({
                'status': 'ok',
            })

    def _assign(self, trans, organizer, code):
        try:
            if '-' in code:
                event = get_prefix_event_map(organizer=organizer)[code.rsplit('-', 1)[0]]
                trans.order = self.order_qs().get(code=code.rsplit('-', 1)[1], event=event)
            else:
                trans.order = self.order_qs().get(code=code.rsplit('-', 1)[-1])
        except Order.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': _('Unknown order code')
            })
        else:
            return self._retry(trans)

    def _comment(self, trans, comment):
        from pretix.base.templatetags.rich_text import rich_text
        trans.comment = comment
        trans.save()
        return JsonResponse({
            'status': 'ok',
            'comment': rich_text(comment),
            'plain': comment,
        })

    def post(self, request, *args, **kwargs):
        for k, v in request.POST.items():
            if not k.startswith('action_'):
                continue
            if 'event' in kwargs:
                trans = get_object_or_404(BankTransaction, id=k.split('_')[1], event=request.event)
            else:
                trans = get_object_or_404(BankTransaction, id=k.split('_')[1], organizer=request.organizer)

            if v == 'discard' and trans.state in (BankTransaction.STATE_INVALID, BankTransaction.STATE_ERROR,
                                                  BankTransaction.STATE_NOMATCH, BankTransaction.STATE_DUPLICATE):
                return self._discard(trans)

            elif v == 'accept' and trans.state == BankTransaction.STATE_INVALID:
                # Accept anyway even with wrong amount
                return self._accept_ignore_amount(trans)

            elif v.startswith('comment:'):
                return self._comment(trans, v[8:])

            elif v.startswith('assign:') and trans.state == BankTransaction.STATE_NOMATCH:
                return self._assign(trans, request.organizer, v[7:])

            elif v == 'retry' and trans.state in (BankTransaction.STATE_ERROR, BankTransaction.STATE_DUPLICATE):
                return self._retry(trans)

            return JsonResponse({
                'status': 'error',
                'message': 'Unknown action'
            })

    def get(self, request, *args, **kwargs):
        u = request.GET.get('query', '')
        if len(u) < 2:
            return JsonResponse({'results': []})

        if "-" in u:
            code = (Q(event__slug__icontains=u.split("-")[0])
                    & Q(code__icontains=Order.normalize_code(u.split("-")[1])))
        else:
            code = Q(code__icontains=Order.normalize_code(u))
        qs = self.order_qs().order_by('pk').annotate(inr=Concat('invoices__prefix', 'invoices__invoice_no')).filter(
            code
            | Q(email__icontains=u)
            | Q(all_positions__attendee_name_cached__icontains=u)
            | Q(all_positions__attendee_email__icontains=u)
            | Q(invoice_address__name_cached__icontains=u)
            | Q(invoice_address__company__icontains=u)
            | Q(invoices__invoice_no=u)
            | Q(invoices__invoice_no=u.zfill(5))
            | Q(inr=u)
        ).select_related('event').annotate(pcnt=Count('invoices')).distinct()
        # Yep, we wouldn't need to count the invoices here. However, having this Count() statement in there
        # tricks Django into generating a GROUP BY clause that it otherwise wouldn't and that is required to
        # avoid duplicate results. Yay?

        return JsonResponse({
            'results': [
                {
                    'code': o.event.slug.upper() + '-' + o.code,
                    'status': o.get_status_display(),
                    'total': money_filter(o.total, o.event.currency)
                } for o in qs
            ]
        })

    def order_qs(self):
        return self.request.event.orders


class JobDetailView(DetailView):
    template_name = 'pretixplugins/banktransfer/job_detail.html'
    permission = 'can_change_orders'
    context_objectname = 'job'

    def redirect_form(self):
        kwargs = {
            'organizer': self.request.organizer.slug,
        }
        if 'event' in self.kwargs:
            kwargs['event'] = self.kwargs['event']
        return redirect(reverse('plugins:banktransfer:import', kwargs=kwargs))

    def redirect_back(self):
        kwargs = {
            'organizer': self.request.organizer.slug,
            'job': self.kwargs['job']
        }
        if 'event' in self.kwargs:
            kwargs['event'] = self.kwargs['event']
        return redirect(reverse('plugins:banktransfer:import.job', kwargs=kwargs))

    @cached_property
    def job(self):
        if 'event' in self.kwargs:
            kwargs = {'event': self.request.event}
        else:
            kwargs = {'organizer': self.request.organizer}
        return get_object_or_404(BankImportJob, id=self.kwargs['job'], **kwargs)

    def get(self, request, *args, **kwargs):
        if 'ajax' in request.GET:
            return JsonResponse({
                'state': self.job.state
            })

        context = self.get_context_data()
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        ctx = {}

        qs = self.job.transactions.select_related('order', 'order__event')

        ctx['transactions_valid'] = qs.filter(state=BankTransaction.STATE_VALID).count()
        ctx['transactions_invalid'] = qs.filter(state__in=[
            BankTransaction.STATE_INVALID, BankTransaction.STATE_ERROR
        ]).count()
        ctx['transactions_ignored'] = qs.filter(state__in=[
            BankTransaction.STATE_DUPLICATE, BankTransaction.STATE_NOMATCH
        ]).count()
        ctx['job'] = self.job
        ctx['organizer'] = self.request.organizer

        if 'event' in self.kwargs:
            ctx['basetpl'] = 'pretixplugins/banktransfer/import_base.html'
        else:
            ctx['basetpl'] = 'pretixplugins/banktransfer/import_base_organizer.html'

        return ctx


class ImportView(ListView):
    template_name = 'pretixplugins/banktransfer/import_form.html'
    permission = 'can_change_orders'
    context_object_name = 'transactions_unhandled'
    paginate_by = 30

    def get_queryset(self):
        if 'event' in self.kwargs:
            qs = BankTransaction.objects.filter(
                Q(event=self.request.event)
            )
        else:
            qs = BankTransaction.objects.filter(
                Q(organizer=self.request.organizer)
            )
        qs = qs.select_related('order').filter(state__in=[
            BankTransaction.STATE_INVALID, BankTransaction.STATE_ERROR,
            BankTransaction.STATE_DUPLICATE, BankTransaction.STATE_NOMATCH
        ])
        if 'search' in self.request.GET:
            q = self.request.GET.get('search')
            qs = qs.filter(
                Q(payer__icontains=q) | Q(reference__icontains=q) | Q(comment__icontains=q)
            ).order_by(
                '-import_job__created'
            )

        return qs

    def discard_all(self):
        self.get_queryset().update(payer='', reference='', state=BankTransaction.STATE_DISCARDED)
        messages.success(self.request, _('All unresolved transactions have been discarded.'))

    def post(self, *args, **kwargs):
        if self.request.POST.get('discard', '') == 'all':
            self.discard_all()
            return self.redirect_back()

        elif ('file' in self.request.FILES and '.csv' in self.request.FILES.get('file').name.lower()) \
                or 'amount' in self.request.POST:
            # Process CSV
            return self.process_csv()

        elif 'file' in self.request.FILES and (
            '.txt' in self.request.FILES.get('file').name.lower()
            or '.sta' in self.request.FILES.get('file').name.lower()
        ):
            return self.process_mt940()

        elif self.request.FILES.get('file') is None:
            messages.error(self.request, _('You must choose a file to import.'))
            return self.redirect_back()

        else:
            messages.error(self.request, _('We were unable to detect the file type of this import. Please '
                                           'contact support for help.'))
            return self.redirect_back()

    @cached_property
    def settings(self):
        return SettingsSandbox('payment', 'banktransfer', getattr(self.request, 'event', self.request.organizer))

    def process_mt940(self):
        try:
            return self.start_processing(mt940import.parse(self.request.FILES.get('file')))
        except:
            logger.exception('Failed to import MT940 file')
            messages.error(self.request, _('We were unable to process your input.'))
            return self.redirect_back()

    def process_csv_file(self):
        o = getattr(self.request, 'event', self.request.organizer)
        try:
            data = csvimport.get_rows_from_file(self.request.FILES['file'])
        except csv.Error as e:  # TODO: narrow down
            logger.error('Import failed: ' + str(e))
            messages.error(self.request, _('I\'m sorry, but we were unable to import this CSV file. Please '
                                           'contact support for help.'))
            return self.redirect_back()

        if len(data) == 0:
            messages.error(self.request, _('I\'m sorry, but we detected this file as empty. Please '
                                           'contact support for help.'))

        if o.settings.get('banktransfer_csvhint') is not None:
            hint = o.settings.get('banktransfer_csvhint', as_type=dict)

            try:
                parsed, good = csvimport.parse(data, hint)
            except csvimport.HintMismatchError:  # TODO: narrow down
                logger.exception('Import using stored hint failed')
            else:
                if good:
                    return self.start_processing(parsed)

        return self.assign_view(data)

    def process_csv_hint(self):
        try:
            data = json.loads(self.request.POST.get('data').strip())
        except ValueError:
            messages.error(self.request, _('Invalid input data.'))
            return self.get(self.request, *self.args, **self.kwargs)

        if 'reference' not in self.request.POST:
            messages.error(self.request, _('You need to select the column containing the payment reference.'))
            return self.assign_view(data)
        try:
            hint = csvimport.new_hint(self.request.POST)
        except Exception as e:
            logger.error('Parsing hint failed: ' + str(e))
            messages.error(self.request, _('We were unable to process your input.'))
            return self.assign_view(data)
        o = getattr(self.request, 'event', self.request.organizer)
        try:
            o.settings.set('banktransfer_csvhint', hint)
        except Exception as e:  # TODO: narrow down
            logger.error('Import using stored hint failed: ' + str(e))
            pass
        else:
            parsed, __ = csvimport.parse(data, hint)
            return self.start_processing(parsed)

    def process_csv(self):
        if 'file' in self.request.FILES:
            return self.process_csv_file()
        elif 'amount' in self.request.POST:
            return self.process_csv_hint()
        return super().get(self.request)

    def assign_view(self, parsed):
        ctx = {
            'json': json.dumps(parsed),
            'rows': parsed,
        }
        if 'event' in self.kwargs:
            ctx['basetpl'] = 'pretixplugins/banktransfer/import_base.html'
        else:
            ctx['basetpl'] = 'pretixplugins/banktransfer/import_base_organizer.html'
            ctx['organizer'] = self.request.organizer
        return render(self.request, 'pretixplugins/banktransfer/import_assign.html', ctx)

    @cached_property
    def job_running(self):
        if 'event' in self.kwargs:
            qs = BankImportJob.objects.filter(
                Q(event=self.request.event) | Q(organizer=self.request.organizer)
            )
        else:
            qs = BankImportJob.objects.filter(
                Q(organizer=self.request.organizer)
            )
        return qs.filter(
            state=BankImportJob.STATE_RUNNING,
            created__lte=now() - timedelta(minutes=30)  # safety timeout
        ).first()

    def redirect_back(self):
        kwargs = {
            'organizer': self.request.organizer.slug
        }
        if 'event' in self.kwargs:
            kwargs['event'] = self.kwargs['event']
        return redirect(reverse('plugins:banktransfer:import', kwargs=kwargs))

    def start_processing(self, parsed):
        if self.job_running:
            messages.error(self.request,
                           _('An import is currently being processed, please try again in a few minutes.'))
            return self.redirect_back()
        if 'event' in self.kwargs:
            job = BankImportJob.objects.create(event=self.request.event, organizer=self.request.organizer)
        else:
            job = BankImportJob.objects.create(organizer=self.request.organizer)
        process_banktransfers.apply_async(kwargs={
            'job': job.pk,
            'data': parsed
        })
        kwargs = {
            'organizer': self.request.organizer.slug,
            'job': job.pk
        }
        if 'event' in self.kwargs:
            kwargs['event'] = self.kwargs['event']
        return redirect(reverse('plugins:banktransfer:import.job', kwargs=kwargs))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['job_running'] = self.job_running
        ctx['no_more_payments'] = False

        if 'event' in self.kwargs:
            ctx['basetpl'] = 'pretixplugins/banktransfer/import_base.html'
            if not self.request.event.has_subevents and self.request.event.settings.get('payment_term_last'):
                if now() > self.request.event.payment_term_last:
                    ctx['no_more_payments'] = True
        else:
            ctx['basetpl'] = 'pretixplugins/banktransfer/import_base_organizer.html'
            ctx['organizer'] = self.request.organizer
        return ctx


class OrganizerBanktransferView:
    def dispatch(self, request, *args, **kwargs):
        if len(request.organizer.events.order_by('currency').values_list('currency', flat=True).distinct()) > 1:
            messages.error(request, _('Please perform per-event bank imports as this organizer has events with '
                                      'multiple currencies.'))
            return redirect('control:organizer', organizer=request.organizer.slug)
        return super().dispatch(request, *args, **kwargs)


class EventImportView(EventPermissionRequiredMixin, ImportView):
    permission = 'can_change_orders'


class OrganizerImportView(OrganizerBanktransferView, OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin,
                          ImportView):
    permission = 'can_change_orders'


class EventJobDetailView(EventPermissionRequiredMixin, JobDetailView):
    permission = 'can_change_orders'


class OrganizerJobDetailView(OrganizerBanktransferView, OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin,
                             JobDetailView):
    permission = 'can_change_orders'


class EventActionView(EventPermissionRequiredMixin, ActionView):
    permission = 'can_change_orders'


class OrganizerActionView(OrganizerBanktransferView, OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin,
                          ActionView):
    permission = 'can_change_orders'

    def order_qs(self):
        all = self.request.user.teams.filter(organizer=self.request.organizer, can_change_orders=True,
                                             can_view_orders=True, all_events=True).exists()
        if self.request.user.has_active_staff_session(self.request.session.session_key) or all:
            return Order.objects.filter(event__organizer=self.request.organizer)
        else:
            return Order.objects.filter(
                event_id__in=self.request.user.teams.filter(
                    organizer=self.request.organizer, can_change_orders=True, can_view_orders=True
                ).values_list('limit_events__id', flat=True)
            )
