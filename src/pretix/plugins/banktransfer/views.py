import csv
import itertools
import json
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Set

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import Concat
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.views.generic import DetailView, FormView, ListView, View
from django.views.generic.detail import SingleObjectMixin
from localflavor.generic.forms import BICFormField, IBANFormField

from pretix.base.forms.widgets import DatePickerWidget
from pretix.base.models import Event, Order, OrderPayment, OrderRefund, Quota
from pretix.base.services.mail import SendMailException
from pretix.base.settings import SettingsSandbox
from pretix.base.templatetags.money import money_filter
from pretix.control.permissions import (
    EventPermissionRequiredMixin, OrganizerPermissionRequiredMixin,
)
from pretix.control.views.organizer import OrganizerDetailViewMixin
from pretix.helpers.json import CustomJSONEncoder
from pretix.plugins.banktransfer import csvimport, mt940import
from pretix.plugins.banktransfer.models import (
    BankImportJob, BankTransaction, RefundExport,
)
from pretix.plugins.banktransfer.payment import BankTransfer
from pretix.plugins.banktransfer.refund_export import (
    build_sepa_xml, get_refund_export_csv,
)
from pretix.plugins.banktransfer.tasks import process_banktransfers

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
        if trans.amount < Decimal('0.00'):
            ref = trans.order.refunds.filter(
                amount=trans.amount * -1,
                provider='manual',
                state__in=(OrderRefund.REFUND_STATE_CREATED, OrderRefund.REFUND_STATE_CREATED)
            ).first()
            p = trans.order.payments.filter(
                amount=trans.amount * -1,
                provider='banktransfer',
                state__in=(OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_REFUNDED)
            ).first()
            if ref:
                ref.done(user=self.request.user)
                trans.state = BankTransaction.STATE_VALID
                trans.save()
                return JsonResponse({
                    'status': 'ok',
                })
            elif p:
                p.create_external_refund(
                    amount=trans.amount * -1,
                    info=json.dumps({
                        'reference': trans.reference,
                        'date': trans.date,
                        'payer': trans.payer,
                        'iban': trans.iban,
                        'bic': trans.bic,
                        'trans_id': trans.pk
                    })
                )
                trans.state = BankTransaction.STATE_VALID
                trans.save()
                return JsonResponse({
                    'status': 'ok',
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': _('Negative amount but refund can\'t be logged, please create manual refund first.')
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
            'iban': trans.iban,
            'bic': trans.bic,
            'trans_id': trans.pk
        }
        try:
            p.confirm(user=self.request.user)
        except Quota.QuotaExceededException:
            pass
        except SendMailException:
            return JsonResponse({
                'status': 'error',
                'message': _('Problem sending email.')
            })
        trans.state = BankTransaction.STATE_VALID
        trans.save()
        trans.order.payments.filter(
            provider='banktransfer',
            state__in=(OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING),
        ).update(state=OrderPayment.PAYMENT_STATE_CANCELED)
        return JsonResponse({
            'status': 'ok',
        })

    def _assign(self, trans, code):
        try:
            if '-' in code:
                trans.order = self.order_qs().get(code=code.rsplit('-', 1)[1], event__slug__iexact=code.rsplit('-', 1)[0])
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

            elif v.startswith('assign:') and trans.state in (BankTransaction.STATE_NOMATCH,
                                                             BankTransaction.STATE_DUPLICATE):
                return self._assign(trans, v[7:])

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


class BankTransactionFilterForm(forms.Form):
    search_text = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': "form-control", "placeholder": _("Search text")}))
    amount_min = forms.DecimalField(required=False, localize=True, widget=forms.TextInput(attrs={'class': "form-control", "placeholder": _("min"), "size": 8}))
    amount_max = forms.DecimalField(required=False, localize=True, widget=forms.TextInput(attrs={'class': "form-control", "placeholder": _("max"), "size": 8}))
    date_min = forms.DateField(required=False, widget=DatePickerWidget(attrs={"size": 8}))
    date_max = forms.DateField(required=False, widget=DatePickerWidget(attrs={"size": 8}))

    def is_valid(self):
        return super().is_valid() and any(value for value in self.cleaned_data.values())

    def filter(self, qs):
        if not self.is_valid():
            raise ValueError(_("Filter form is not valid."))
        if self.cleaned_data.get('search_text'):
            q = self.cleaned_data['search_text']
            qs = qs.filter(Q(payer__icontains=q) | Q(reference__icontains=q) | Q(comment__icontains=q) | Q(iban__icontains=q) | Q(bic__icontains=q))
        if self.cleaned_data.get('amount_min') is not None:
            qs = qs.filter(amount__gte=self.cleaned_data['amount_min'])
        if self.cleaned_data.get("amount_max") is not None:
            qs = qs.filter(amount__lte=self.cleaned_data['amount_max'])
        if self.cleaned_data.get('date_min') is not None:
            qs = qs.filter(ate_parsed__gte=self.cleaned_data['date_min'])
        if self.cleaned_data.get('date_max') is not None:
            qs = qs.filter(date_parsed__lte=self.cleaned_data['date_max'])
        return qs


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

        filter_form = BankTransactionFilterForm(self.request.GET or None)
        if filter_form.is_valid():
            qs = filter_form.filter(qs)

        return qs.order_by('-import_job__created')

    def discard_all(self):
        self.get_queryset().update(payer='', reference='', state=BankTransaction.STATE_DISCARDED)
        messages.success(self.request, _('All unresolved transactions have been discarded.'))

    def post(self, *args, **kwargs):
        if self.request.POST.get('discard', '') == 'all':
            self.discard_all()
            return self.redirect_back()

        elif ('file' in self.request.FILES and '.csv' in self.request.FILES.get('file').name.lower()) or 'amount' in self.request.POST:
            # Process CSV
            return self.process_csv()

        elif 'file' in self.request.FILES and (
            '.txt' in self.request.FILES.get('file').name.lower()
            or '.sta' in self.request.FILES.get('file').name.lower()
            or '.swi' in self.request.FILES.get('file').name.lower()  # Rabobank's MT940 Structured
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
        ctx['filter_form'] = BankTransactionFilterForm(self.request.GET or None)

        if 'event' in self.kwargs:
            ctx['basetpl'] = 'pretixplugins/banktransfer/import_base.html'
            if not self.request.event.has_subevents and self.request.event.settings.get('payment_term_last'):
                if now() > self.request.event.payment_term_last:
                    ctx['no_more_payments'] = True
            ctx['lastimport'] = BankImportJob.objects.filter(
                state=BankImportJob.STATE_COMPLETED,
                organizer=self.request.organizer,
                event=self.request.event
            ).order_by('created').last()
            ctx['runningimport'] = BankImportJob.objects.filter(
                state__in=[BankImportJob.STATE_PENDING, BankImportJob.STATE_RUNNING],
                organizer=self.request.organizer,
                event=self.request.event
            ).order_by('created').last()
        else:
            ctx['lastimport'] = BankImportJob.objects.filter(
                state=BankImportJob.STATE_COMPLETED,
                organizer=self.request.organizer,
                event__isnull=True
            ).order_by('created').last()
            ctx['runningimport'] = BankImportJob.objects.filter(
                state__in=[BankImportJob.STATE_PENDING, BankImportJob.STATE_RUNNING],
                organizer=self.request.organizer,
                event__isnull=True
            ).order_by('created').last()
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


def _row_key_func(row):
    return row['iban'], row['bic']


def _unite_transaction_rows(transaction_rows):
    united_transactions_rows = []
    transaction_rows = sorted(transaction_rows, key=_row_key_func)
    for (iban, bic), group in itertools.groupby(transaction_rows, _row_key_func):
        rows = list(group)
        united_transactions_rows.append({
            "iban": iban,
            "bic": bic,
            "id": ", ".join(sorted(set(r['id'] for r in rows))),
            "payer": ", ".join(sorted(set(r['payer'] for r in rows))),
            "amount": sum(r['amount'] for r in rows),
        })
    return united_transactions_rows


class RefundExportListView(ListView):
    template_name = 'pretixplugins/banktransfer/refund_export.html'
    model = RefundExport
    context_object_name = 'exports'

    def get_success_url(self):
        raise NotImplementedError

    def get_unexported(self) -> QuerySet:
        raise NotImplementedError()

    def dispatch(self, request, *args, **kwargs):
        if len(request.organizer.events.order_by('currency').values_list('currency', flat=True).distinct()) > 1:
            messages.error(request, _('Please perform per-event refund exports as this organizer has events with '
                                      'multiple currencies.'))
            return redirect('control:organizer', organizer=request.organizer.slug)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['num_new'] = self.get_unexported().count()
        ctx['basetpl'] = "pretixcontrol/event/base.html"
        if not hasattr(self.request, 'event'):
            ctx['basetpl'] = "pretixcontrol/organizers/base.html"
        return ctx

    @transaction.atomic()
    def post(self, request, *args, **kwargs):
        unite_transactions = request.POST.get("unite_transactions", False)
        valid_refunds: Set[OrderRefund] = set()
        for refund in self.get_unexported().select_related('order', 'order__event'):
            if not refund.info_data:
                # Should not happen
                messages.warning(request,
                                 _("We could not find bank account information for the refund {refund_id}. It was marked as failed.")
                                 .format(refund_id=refund.full_id))
                refund.state = OrderRefund.REFUND_STATE_FAILED
                refund.save()
                continue
            else:
                valid_refunds.add(refund)

        if valid_refunds:
            transaction_rows = []

            for refund in valid_refunds:
                data = refund.info_data
                transaction_rows.append({
                    "amount": refund.amount,
                    "id": refund.full_id,
                    **{key: data[key] for key in ("payer", "iban", "bic")}
                })
                refund.done(user=self.request.user)

            if unite_transactions:
                transaction_rows = _unite_transaction_rows(transaction_rows)

            rows_data = json.dumps(transaction_rows, cls=CustomJSONEncoder)
            if hasattr(request, 'event'):
                RefundExport.objects.create(event=self.request.event, testmode=self.request.event.testmode, rows=rows_data)
            else:
                RefundExport.objects.create(organizer=self.request.organizer, testmode=False, rows=rows_data)

        else:
            messages.warning(request, _('No valid orders have been found.'))

        return redirect(self.get_success_url())


class EventRefundExportListView(EventPermissionRequiredMixin, RefundExportListView):
    permission = 'can_change_orders'

    def get_success_url(self):
        return reverse('plugins:banktransfer:refunds.list', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
        })

    def get_queryset(self):
        return RefundExport.objects.filter(
            event=self.request.event
        ).order_by('-datetime')

    def get_unexported(self):
        return OrderRefund.objects.filter(
            order__event=self.request.event,
            provider='banktransfer',
            state=OrderRefund.REFUND_STATE_CREATED,
            order__testmode=self.request.event.testmode,
        )


class OrganizerRefundExportListView(OrganizerPermissionRequiredMixin, RefundExportListView):
    permission = 'can_change_orders'

    def get_success_url(self):
        return reverse('plugins:banktransfer:refunds.list', kwargs={
            'organizer': self.request.organizer.slug,
        })

    def get_queryset(self):
        return RefundExport.objects.filter(
            Q(organizer=self.request.organizer) | Q(event__organizer=self.request.organizer)
        ).order_by('-datetime')

    def get_unexported(self):
        return OrderRefund.objects.filter(
            order__event__organizer=self.request.organizer,
            provider='banktransfer',
            state=OrderRefund.REFUND_STATE_CREATED,
            order__testmode=False,
        )


class DownloadRefundExportView(DetailView):
    model = RefundExport

    def get(self, request, *args, **kwargs):
        self.object: RefundExport = self.get_object()
        self.object.downloaded = True
        self.object.save(update_fields=["downloaded"])
        filename, content_type, data = get_refund_export_csv(self.object)
        return FileResponse(data, as_attachment=True, filename=filename, content_type=content_type)


class EventDownloadRefundExportView(EventPermissionRequiredMixin, DownloadRefundExportView):
    permission = 'can_change_orders'

    def get_object(self, *args, **kwargs):
        return get_object_or_404(
            RefundExport,
            event=self.request.event,
            pk=self.kwargs.get('id')
        )


class OrganizerDownloadRefundExportView(OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, DownloadRefundExportView):
    permission = 'can_change_orders'

    def get_object(self, *args, **kwargs):
        return get_object_or_404(
            RefundExport,
            organizer=self.request.organizer,
            pk=self.kwargs.get('id')
        )


class SepaXMLExportForm(forms.Form):
    account_holder = forms.CharField(label=_("Account holder"))
    iban = IBANFormField(label="IBAN")
    bic = BICFormField(label="BIC")

    def set_initial_from_event(self, event: Event):
        banktransfer = event.get_payment_providers(cached=True)[BankTransfer.identifier]
        self.initial["account_holder"] = banktransfer.settings.get("bank_details_sepa_name")
        self.initial["iban"] = banktransfer.settings.get("bank_details_sepa_iban")
        self.initial["bic"] = banktransfer.settings.get("bank_details_sepa_bic")


class SepaXMLExportView(SingleObjectMixin, FormView):
    form_class = SepaXMLExportForm
    model = RefundExport
    template_name = 'pretixplugins/banktransfer/sepa_export.html'
    context_object_name = "export"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.object: RefundExport = self.get_object()

    def form_valid(self, form):
        self.object.downloaded = True
        self.object.save(update_fields=["downloaded"])
        filename, content_type, data = build_sepa_xml(self.object, **form.cleaned_data)
        return FileResponse(data, as_attachment=True, filename=filename, content_type=content_type)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['basetpl'] = "pretixcontrol/event/base.html"
        if not hasattr(self.request, 'event'):
            ctx['basetpl'] = "pretixcontrol/organizers/base.html"
        return ctx


class EventSepaXMLExportView(EventPermissionRequiredMixin, SepaXMLExportView):
    permission = 'can_change_orders'

    def get_object(self, *args, **kwargs):
        return get_object_or_404(
            RefundExport,
            event=self.request.event,
            pk=self.kwargs.get('id')
        )

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.set_initial_from_event(self.object.event)
        return form


class OrganizerSepaXMLExportView(OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, SepaXMLExportView):
    permission = 'can_change_orders'

    def get_object(self, *args, **kwargs):
        return get_object_or_404(
            RefundExport,
            organizer=self.request.organizer,
            pk=self.kwargs.get('id')
        )
