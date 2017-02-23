import csv
import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext as _
from django.views.generic import DetailView, ListView, View

from pretix.base.models import Order, Quota
from pretix.base.services.mail import SendMailException
from pretix.base.services.orders import mark_order_paid
from pretix.base.settings import SettingsSandbox
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.plugins.banktransfer import csvimport, mt940import
from pretix.plugins.banktransfer.models import BankImportJob, BankTransaction
from pretix.plugins.banktransfer.tasks import process_banktransfers

logger = logging.getLogger('pretix.plugins.banktransfer')


class ActionView(EventPermissionRequiredMixin, View):
    permission = 'can_change_orders'

    def _discard(self, trans):
        trans.state = BankTransaction.STATE_DISCARDED
        trans.shred_private_data()
        trans.save()
        return JsonResponse({
            'status': 'ok'
        })

    def _retry(self, trans):
        if trans.amount != trans.order.total:
            return JsonResponse({
                'status': 'error',
                'message': _('The transaction amount is incorrect.')
            })
        return self._accept_ignore_amount(trans)

    def _accept_ignore_amount(self, trans):
        if trans.order.status == Order.STATUS_PAID:
            return JsonResponse({
                'status': 'error',
                'message': _('The order is already marked as paid.')
            })
        elif trans.order.status == Order.STATUS_REFUNDED:
            return JsonResponse({
                'status': 'error',
                'message': _('The order has already been refunded.')
            })
        elif trans.order.status == Order.STATUS_CANCELED:
            return JsonResponse({
                'status': 'error',
                'message': _('The order has already been canceled.')
            })

        try:
            mark_order_paid(trans.order, provider='banktransfer', info=json.dumps({
                'reference': trans.reference,
                'date': trans.date,
                'payer': trans.payer,
                'trans_id': trans.pk
            }))
            trans.state = BankTransaction.STATE_VALID
            trans.save()
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
            return JsonResponse({
                'status': 'ok'
            })

    def _assign(self, trans, code):
        try:
            trans.order = self.request.event.orders.get(code=code)
        except Order.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': _('Unknown order code')
            })
        else:
            return self._retry(trans)

    def _comment(self, trans, comment):
        trans.comment = comment
        trans.save()
        return JsonResponse({
            'status': 'ok'
        })

    def post(self, request, *args, **kwargs):
        for k, v in request.POST.items():
            if not k.startswith('action_'):
                continue
            trans = get_object_or_404(BankTransaction, id=k.split('_')[1], event=self.request.event)

            if v == 'discard' and trans.state in (BankTransaction.STATE_INVALID, BankTransaction.STATE_ERROR,
                                                  BankTransaction.STATE_NOMATCH, BankTransaction.STATE_DUPLICATE):
                return self._discard(trans)

            elif v == 'accept' and trans.state == BankTransaction.STATE_INVALID:
                # Accept anyway even with wrong amount
                return self._accept_ignore_amount(trans)

            elif v.startswith('comment:'):
                return self._comment(trans, v[8:])

            elif v.startswith('assign:') and trans.state == BankTransaction.STATE_NOMATCH:
                return self._assign(trans, v[7:])

            elif v == 'retry' and trans.state in (BankTransaction.STATE_ERROR, BankTransaction.STATE_DUPLICATE):
                return self._retry(trans)

            return JsonResponse({
                'status': 'error',
                'message': 'Unknown action'
            })

    def get(self, request, *args, **kwargs):
        from django.utils.formats import localize

        query = request.GET.get('query', '')
        if len(query) < 2:
            return JsonResponse({'results': []})

        qs = self.request.event.orders.filter(Q(code__icontains=query) | Q(code__icontains=Order.normalize_code(query)))
        return JsonResponse({
            'results': [
                {
                    'code': o.code,
                    'status': o.get_status_display(),
                    'total': localize(o.total) + ' ' + self.request.event.currency
                } for o in qs
            ]
        })


class JobDetailView(EventPermissionRequiredMixin, DetailView):
    template_name = 'pretixplugins/banktransfer/job_detail.html'
    permission = 'can_change_orders'
    context_objectname = 'job'

    def redirect_form(self):
        return redirect(reverse('plugins:banktransfer:import', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        }))

    def redirect_back(self):
        return redirect(reverse('plugins:banktransfer:import.job', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'job': self.kwargs['job']
        }))

    def get_object(self, queryset=None):
        return get_object_or_404(BankImportJob, id=self.kwargs['job'], event=self.request.event)

    def get(self, request, *args, **kwargs):
        if 'ajax' in request.GET:
            self.object = self.get_object()
            return JsonResponse({
                'state': self.object.state
            })

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        qs = self.object.transactions.select_related('order')

        ctx['transactions_valid'] = qs.filter(state=BankTransaction.STATE_VALID).count()
        ctx['transactions_invalid'] = qs.filter(state__in=[
            BankTransaction.STATE_INVALID, BankTransaction.STATE_ERROR
        ]).count()
        ctx['transactions_ignored'] = qs.filter(state__in=[
            BankTransaction.STATE_DUPLICATE, BankTransaction.STATE_NOMATCH
        ]).count()
        ctx['job'] = self.object

        return ctx


class ImportView(EventPermissionRequiredMixin, ListView):
    template_name = 'pretixplugins/banktransfer/import_form.html'
    permission = 'can_change_orders'
    context_object_name = 'transactions_unhandled'
    paginate_by = 30

    def get_queryset(self):
        qs = BankTransaction.objects.filter(
            event=self.request.event
        ).select_related('order').filter(state__in=[
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

        elif ('file' in self.request.FILES and 'csv' in self.request.FILES.get('file').name.lower()) \
                or 'amount' in self.request.POST:
            # Process CSV
            return self.process_csv()

        elif 'file' in self.request.FILES and 'txt' in self.request.FILES.get('file').name.lower():
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
        return SettingsSandbox('payment', 'banktransfer', self.request.event)

    def process_mt940(self):
        try:
            return self.start_processing(mt940import.parse(self.request.FILES.get('file')))
        except:
            logger.exception('Failed to import MT940 file')
            messages.error(self.request, _('We were unable to process your input.'))
            return self.redirect_back()

    def process_csv_file(self):
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

        if self.request.event.settings.get('banktransfer_csvhint') is not None:
            hint = self.request.event.settings.get('banktransfer_csvhint', as_type=dict)
            try:
                parsed = csvimport.parse(data, hint)
            except csvimport.HintMismatchError:  # TODO: narrow down
                logger.exception('Import using stored hint failed')
            else:
                return self.start_processing(parsed)

        return self.assign_view(data)

    def process_csv_hint(self):
        data = []
        for i in range(int(self.request.POST.get('rows'))):
            data.append(
                [
                    self.request.POST.get('col[%d][%d]' % (i, j))
                    for j in range(int(self.request.POST.get('cols')))
                ]
            )
        if 'reference' not in self.request.POST:
            messages.error(self.request, _('You need to select the column containing the payment reference.'))
            return self.assign_view(data)
        try:
            hint = csvimport.new_hint(self.request.POST)
        except Exception as e:
            logger.error('Parsing hint failed: ' + str(e))
            messages.error(self.request, _('We were unable to process your input.'))
            return self.assign_view(data)
        try:
            self.request.event.settings.set('banktransfer_csvhint', hint)
        except Exception as e:  # TODO: narrow down
            logger.error('Import using stored hint failed: ' + str(e))
            pass
        else:
            parsed = csvimport.parse(data, hint)
            return self.start_processing(parsed)

    def process_csv(self):
        if 'file' in self.request.FILES:
            return self.process_csv_file()
        elif 'amount' in self.request.POST:
            return self.process_csv_hint()
        return super().get(self.request)

    def assign_view(self, parsed):
        return render(self.request, 'pretixplugins/banktransfer/import_assign.html', {
            'rows': parsed
        })

    @cached_property
    def job_running(self):
        return BankImportJob.objects.filter(
            event=self.request.event, state=BankImportJob.STATE_RUNNING,
            created__lte=now() - timedelta(minutes=30)  # safety timeout
        ).first()

    def redirect_back(self):
        return redirect(reverse('plugins:banktransfer:import', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
        }))

    def start_processing(self, parsed):
        if self.job_running:
            messages.error(self.request, _('An import is currently being processed, please try again in a few minutes.'))
            return self.redirect_back()
        job = BankImportJob.objects.create(event=self.request.event)
        process_banktransfers.apply_async(kwargs={
            'event': self.request.event.pk,
            'job': job.pk,
            'data': parsed
        })
        return redirect(reverse('plugins:banktransfer:import.job', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'job': job.pk
        }))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['job_running'] = self.job_running
        ctx['no_more_payments'] = False
        if self.request.event.settings.get('payment_term_last'):
            if now() > self.request.event.payment_term_last:
                ctx['no_more_payments'] = True
        return ctx
