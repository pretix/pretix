import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from pretix.base.models import CachedFile
from pretix.base.services.orderimport import import_orders, parse_csv
from pretix.base.views.tasks import AsyncAction
from pretix.control.forms.orderimport import ProcessForm
from pretix.control.permissions import EventPermissionRequiredMixin

logger = logging.getLogger(__name__)


class ImportView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/orders/import_start.html'
    permission = 'can_change_orders'

    def post(self, request, *args, **kwargs):
        if 'file' not in request.FILES:
            return redirect(reverse('control:event.orders.import', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
            }))
        if not request.FILES['file'].name.lower().endswith('.csv'):
            messages.error(request, _('Please only upload CSV files.'))
            return redirect(reverse('control:event.orders.import', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
            }))
        if request.FILES['file'].size > 1024 * 1024 * 10:
            messages.error(request, _('Please do not upload files larger than 10 MB.'))
            return redirect(reverse('control:event.orders.import', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
            }))

        cf = CachedFile.objects.create(
            expires=now() + timedelta(days=1),
            date=now(),
            filename='import.csv',
            type='text/csv',
        )
        cf.file.save('import.csv', request.FILES['file'])
        return redirect(reverse('control:event.orders.import.process', kwargs={
            'event': request.event.slug,
            'organizer': request.organizer.slug,
            'file': cf.id
        }))


class ProcessView(EventPermissionRequiredMixin, AsyncAction, FormView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/orders/import_process.html'
    form_class = ProcessForm
    task = import_orders
    known_errortypes = ['DataImportError']

    def get_form_kwargs(self):
        k = super().get_form_kwargs()
        k.update({
            'event': self.request.event,
            'initial': self.request.event.settings.order_import_settings,
            'headers': self.parsed.fieldnames
        })
        return k

    def form_valid(self, form):
        self.request.event.settings.order_import_settings = form.cleaned_data
        return self.do(
            self.request.event.pk, self.file.id, form.cleaned_data, self.request.LANGUAGE_CODE,
            self.request.user.pk
        )

    @cached_property
    def file(self):
        return get_object_or_404(CachedFile, pk=self.kwargs.get("file"), filename="import.csv")

    @cached_property
    def parsed(self):
        return parse_csv(self.file.file, 1024 * 1024)

    def get(self, request, *args, **kwargs):
        if 'async_id' in request.GET and settings.HAS_CELERY:
            return self.get_result(request)
        return FormView.get(self, request, *args, **kwargs)

    def get_success_message(self, value):
        return _('The import was successful.')

    def get_success_url(self, value):
        return reverse('control:event.orders', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
        })

    def dispatch(self, request, *args, **kwargs):
        if not self.parsed:
            messages.error(request, _('We\'ve been unable to parse the uploaded file as a CSV file.'))
            return redirect(reverse('control:event.orders.import', kwargs={
                'event': request.event.slug,
                'organizer': request.organizer.slug,
            }))
        return super().dispatch(request, *args, **kwargs)

    def get_error_url(self):
        return reverse('control:event.orders.import.process', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.organizer.slug,
            'file': self.file.id
        })

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['file'] = self.file
        ctx['parsed'] = self.parsed
        ctx['sample_rows'] = list(self.parsed)[:3]
        return ctx
