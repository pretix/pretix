import csv
import json
import logging
import re
import shutil
import sys
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import TemplateView

from pretix.base.models import Order, Quota
from pretix.base.services.orders import mark_order_paid
from pretix.base.settings import SettingsSandbox
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.plugins.banktransfer import csvimport, hbci, mt940import

logger = logging.getLogger('pretix.plugins.banktransfer')


class HbciForm(forms.Form):
    hbci_blz = forms.CharField(label=_("Bank code"))
    hbci_userid = forms.CharField(label=_("User ID"))
    hbci_customerid = forms.CharField(label=_("Customer ID"), required=False)
    hbci_tokentype = forms.CharField(label=_("Token type"), initial='pintan')
    hbci_tokenname = forms.CharField(label=_("Token name"), required=False)
    hbci_server = forms.URLField(label=_("Server URL"))
    hbci_version = forms.IntegerField(label=_("HBCI version"), required=False, initial=220)
    pin = forms.CharField(label=_("PIN"), widget=forms.PasswordInput)


class ImportView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/banktransfer/import_form.html'
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if 'hbci_server' in self.request.POST:
            return self.process_hbci()

        if ('file' in self.request.FILES and 'csv' in self.request.FILES.get('file').name.lower()) \
                or 'amount' in self.request.POST:
            # Process CSV
            return self.process_csv()

        if 'file' in self.request.FILES and 'txt' in self.request.FILES.get('file').name.lower():
            return self.process_mt940()

        if 'confirm' in self.request.POST:
            orders = Order.objects.current.filter(event=self.request.event,
                                                  code__in=self.request.POST.getlist('mark_paid'))
            some_failed = False
            for order in orders:
                try:
                    mark_order_paid(order, provider='banktransfer', info=json.dumps({
                        'reference': self.request.POST.get('reference_%s' % order.code),
                        'date': self.request.POST.get('date_%s' % order.code),
                        'payer': self.request.POST.get('payer_%s' % order.code),
                        'import': now().isoformat(),
                    }))
                except Quota.QuotaExceededException:
                    some_failed = True

            if some_failed:
                messages.warning(self.request, _('Not all of the selected orders could be marked as '
                                                 'paid as some of them have expired and the selected '
                                                 'items are sold out.'))
            else:
                messages.success(self.request, _('The selected orders have been marked as paid.'))
                # TODO: Display a list of them!
            return self.redirect_back()

        messages.error(self.request, _('We were unable to detect the file type of this import. Please '
                                       'contact support for help.'))
        return self.redirect_back()

    @cached_property
    def settings(self):
        return SettingsSandbox('payment', 'banktransfer', self.request.event)

    def process_hbci(self):
        form = HbciForm(data=self.request.POST if self.request.method == "POST" else None,
                        initial=self.settings)
        if form.is_valid():
            for key, value in form.cleaned_data.items():
                if key.startswith('hbci_'):
                    self.settings.set(key, value)
            data, log = hbci.hbci_transactions(self.request.event, form.cleaned_data)
            if data:
                return self.confirm_view(data)
            return render(self.request, 'pretixplugins/banktransfer/hbci_log.html', {
                'log': log
            })
        else:
            return self.get(*self.args, **self.kwargs)

    def process_mt940(self):
        return self.confirm_view(mt940import.parse(self.request.FILES.get('file')))

    @cached_property
    def hbci_form(self):
        return HbciForm(data=self.request.POST if self.request.method == "POST" else None,
                        initial=self.settings)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['hbci_available'] = shutil.which('aqbanking-cli') and shutil.which('aqhbci-tool4')
        if ctx['hbci_available']:
            ctx['hbci_form'] = self.hbci_form
        return ctx

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
            except csvimport.HintMismatchError as e:  # TODO: narrow down
                logger.error('Import using stored hint failed: ' + str(e))
            else:
                return self.confirm_view(parsed)

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
            return self.confirm_view(parsed)

    def process_csv(self):
        if 'file' in self.request.FILES:
            return self.process_csv_file()
        elif 'amount' in self.request.POST:
            return self.process_csv_hint()
        return super().get(self.request)

    def confirm_view(self, parsed):
        parsed = self.annotate_data(parsed)
        return render(self.request, 'pretixplugins/banktransfer/import_confirm.html', {
            'rows': parsed
        })

    def assign_view(self, parsed):
        return render(self.request, 'pretixplugins/banktransfer/import_assign.html', {
            'rows': parsed
        })

    def redirect_back(self):
        return redirect('plugins:banktransfer:import',
                        event=self.request.event.slug,
                        organizer=self.request.event.organizer.slug)

    def annotate_data(self, data):
        pattern = re.compile(self.request.event.slug.upper() + "[ ]*([A-Z0-9]{5})")
        amount_pattern = re.compile("[^0-9.-]")
        for row in data:
            row['ok'] = False
            match = pattern.search(row['reference'].upper())
            try:
                amount = Decimal(amount_pattern.sub("", row['amount'].replace(",", ".")))
            except:
                logger.exception('Could not parse amount of transaction')
                amount = 0
            if not match:
                row['class'] = 'warning' if amount > 0 else ''
                row['message'] = _('No order code detected')
                continue

            code = match.group(1)
            try:
                order = Order.objects.current.get(event=self.request.event,
                                                  code=code)
            except Order.DoesNotExist:
                row['class'] = 'danger'
                row['message'] = _('Unknown order code detected')
            else:
                row['order'] = order
                if order.status == Order.STATUS_PENDING:
                    if amount != order.total:
                        row['class'] = 'danger'
                        row['message'] = _('Found wrong amount. Expected: %s' % str(order.total))
                    else:
                        row['class'] = 'success'
                        row['message'] = _('Valid payment')
                        row['ok'] = True
                elif order.status == Order.STATUS_CANCELLED:
                    row['class'] = 'danger'
                    row['message'] = _('Order has been cancelled')
                elif order.status == Order.STATUS_PAID:
                    row['class'] = ''
                    row['message'] = _('Order already has been paid')
                elif order.status == Order.STATUS_REFUNDED:
                    row['class'] = 'warning'
                    row['message'] = _('Order has been refunded')
        return data
