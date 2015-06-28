import csv
from decimal import Decimal
import json
import logging
import re

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.timezone import now
from django.views.generic import TemplateView
from pretix.base.models import Order, Quota
from pretix.base.services.orders import mark_order_paid
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.plugins.banktransfer import csvimport, mt940import
from django.utils.translation import ugettext_lazy as _


logger = logging.getLogger('pretix.plugins.banktransfer')


class ImportView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixplugins/banktransfer/import_form.html'
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if ('file' in self.request.FILES and 'csv' in self.request.FILES.get('file').name.lower()) \
                or 'amount' in self.request.POST:
            # Process CSV
            return self.process_csv()

        if 'file' in self.request.FILES and 'txt' in self.request.FILES.get('file').name.lower():
            return self.process_mt940()

        if 'confirm' in self.request.POST:
            orders = Order.objects.filter(event=self.request.event,
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
                messages.success(self.request, _('The selected orders have been marked as paid.'))
            else:
                messages.warning(self.request, _('Not all of the selected orders could be marked as '
                                                 'paid as some of them have expired and the selected '
                                                 'items are sold out.'))
                # TODO: Display a list of them!
            return self.redirect_back()

        messages.error(self.request, _('We were unable to detect the file type of this import. Please '
                                       'contact support for help.'))
        return self.redirect_back()

    def process_mt940(self):
        return self.confirm_view(mt940import.parse(self.request.FILES.get('file')))

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
            data.append([
                self.request.POST.get('col[%d][%d]' % (i, j))
                for j in range(int(self.request.POST.get('cols')))
            ])
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
        pattern = re.compile(self.request.event.slug.upper() + "([A-Z0-9]{5})")
        amount_pattern = re.compile("[^0-9.-]")
        for row in data:
            row['ok'] = False
            match = pattern.search(row['reference'].upper())
            if not match:
                row['class'] = ''
                row['message'] = _('No order code detected')
                continue

            code = match.group(1)
            try:
                order = Order.objects.current.get(event=self.request.event,
                                                  code=code)
            except Order.DoesNotExist:
                row['class'] = 'error'
                row['message'] = _('Unknown order code detected')
            else:
                row['order'] = order
                if order.status == Order.STATUS_PENDING:
                    amount = Decimal(amount_pattern.sub("", row['amount'].replace(",", ".")))
                    if amount != order.total:
                        row['class'] = 'error'
                        row['message'] = _('Found wrong amount. Expected: %s' % str(order.total))
                    else:
                        row['class'] = 'success'
                        row['message'] = _('Valid payment')
                        row['ok'] = True
                elif order.status == Order.STATUS_CANCELLED:
                    row['class'] = 'error'
                    row['message'] = _('Order has been cancelled')
                elif order.status == Order.STATUS_PAID:
                    # TODO: Do a plausibility check to tell duplicate payments from overlapping import files
                    row['class'] = ''
                    row['message'] = _('Order already has been paid')
                elif order.status == Order.STATUS_REFUNDED:
                    row['class'] = 'warning'
                    row['message'] = _('Order has been refunded')
        return data
