import io

from defusedcsv import csv
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import resolve, reverse
from django.db import transaction
from django.db.models import Sum
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect,
    JsonResponse,
)
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views.generic import (
    CreateView, DeleteView, ListView, TemplateView, UpdateView, View,
)

from pretix.base.models import LogEntry, Voucher
from pretix.base.models.vouchers import _generate_random_code
from pretix.control.forms.filter import VoucherFilterForm
from pretix.control.forms.vouchers import VoucherBulkForm, VoucherForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.signals import voucher_form_class
from pretix.control.views import PaginationMixin


class VoucherList(PaginationMixin, EventPermissionRequiredMixin, ListView):
    model = Voucher
    context_object_name = 'vouchers'
    template_name = 'pretixcontrol/vouchers/index.html'
    permission = 'can_view_vouchers'

    def get_queryset(self):
        qs = self.request.event.vouchers.all().select_related('item', 'variation')
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return VoucherFilterForm(data=self.request.GET, event=self.request.event)

    def get(self, request, *args, **kwargs):
        if request.GET.get("download", "") == "yes":
            return self._download_csv()
        return super().get(request, *args, **kwargs)

    def _download_csv(self):
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        headers = [
            _('Voucher code'), _('Valid until'), _('Product'), _('Reserve quota'), _('Bypass quota'),
            _('Price effect'), _('Value'), _('Tag'), _('Redeemed'), _('Maximum usages')
        ]
        writer.writerow(headers)

        for v in self.get_queryset():
            if v.item:
                if v.variation:
                    prod = '%s – %s' % (str(v.item.name), str(v.variation.name))
                else:
                    prod = '%s' % str(v.item.name)
            elif v.quota:
                prod = _('Any product in quota "{quota}"').format(quota=str(v.quota.name))
            row = [
                v.code,
                v.valid_until.isoformat() if v.valid_until else "",
                prod,
                _("Yes") if v.block_quota else _("No"),
                _("Yes") if v.allow_ignore_quota else _("No"),
                v.get_price_mode_display(),
                str(v.value) if v.value is not None else "",
                v.tag,
                str(v.redeemed),
                str(v.max_usages)
            ]
            writer.writerow(row)

        r = HttpResponse(output.getvalue().encode("utf-8"), content_type='text/csv')
        r['Content-Disposition'] = 'attachment; filename="vouchers.csv"'
        return r


class VoucherTags(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/vouchers/tags.html'
    permission = 'can_view_vouchers'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        tags = self.request.event.vouchers.order_by('tag').filter(tag__isnull=False).values('tag').annotate(
            total=Sum('max_usages'),
            redeemed=Sum('redeemed')
        )
        for t in tags:
            t['percentage'] = int((t['redeemed'] / t['total']) * 100)

        ctx['tags'] = tags
        return ctx


class VoucherDelete(EventPermissionRequiredMixin, DeleteView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/delete.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def get_object(self, queryset=None) -> Voucher:
        try:
            return self.request.event.vouchers.get(
                id=self.kwargs['voucher']
            )
        except Voucher.DoesNotExist:
            raise Http404(_("The requested voucher does not exist."))

    def get(self, request, *args, **kwargs):
        if not self.get_object().allow_delete():
            messages.error(request, _('A voucher can not be deleted if it already has been redeemed.'))
            return HttpResponseRedirect(self.get_success_url())
        return super().get(request, *args, **kwargs)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        if not self.object.allow_delete():
            messages.error(request, _('A voucher can not be deleted if it already has been redeemed.'))
        else:
            self.object.log_action('pretix.voucher.deleted', user=self.request.user)
            self.object.delete()
            messages.success(request, _('The selected voucher has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class VoucherUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/detail.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def get_form_class(self):
        form_class = VoucherForm
        for receiver, response in voucher_form_class.send(self.request.event, cls=form_class):
            if response:
                form_class = response
        return form_class

    def get_object(self, queryset=None) -> VoucherForm:
        url = resolve(self.request.path_info)
        try:
            return self.request.event.vouchers.get(
                id=url.kwargs['voucher']
            )
        except Voucher.DoesNotExist:
            raise Http404(_("The requested voucher does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.voucher.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class VoucherCreate(EventPermissionRequiredMixin, CreateView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/detail.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def get_form_class(self):
        form_class = VoucherForm
        for receiver, response in voucher_form_class.send(self.request.event, cls=form_class):
            if response:
                form_class = response
        return form_class

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = Voucher(event=self.request.event)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new voucher has been created: {code}').format(code=form.instance.code))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.voucher.added', data=dict(form.cleaned_data), user=self.request.user)
        return ret

    def post(self, request, *args, **kwargs):
        # TODO: Transform this into an asynchronous call?
        with request.event.lock():
            return super().post(request, *args, **kwargs)


class VoucherBulkCreate(EventPermissionRequiredMixin, CreateView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/bulk.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = Voucher(event=self.request.event)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        log_entries = []
        form.save(self.request.event)
        # We need to query them again as form.save() uses bulk_create which does not fill in .pk values on databases
        # other than PostgreSQL
        for v in self.request.event.vouchers.filter(code__in=form.cleaned_data['codes']):
            log_entries.append(
                v.log_action('pretix.voucher.added', data=form.cleaned_data, user=self.request.user, save=False)
            )
        LogEntry.objects.bulk_create(log_entries)
        messages.success(self.request, _('The new vouchers have been created.'))
        return HttpResponseRedirect(self.get_success_url())

    def get_form_class(self):
        form_class = VoucherBulkForm
        for receiver, response in voucher_form_class.send(self.request.event, cls=form_class):
            if response:
                form_class = response
        return form_class

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['code_length'] = settings.ENTROPY['voucher_code']
        return ctx

    def post(self, request, *args, **kwargs):
        # TODO: Transform this into an asynchronous call?
        with request.event.lock():
            return super().post(request, *args, **kwargs)


class VoucherRNG(EventPermissionRequiredMixin, View):
    permission = 'can_change_vouchers'

    def get(self, request, *args, **kwargs):
        codes = set()
        try:
            num = int(request.GET.get('num', '5'))
        except ValueError:  # NOQA
            return HttpResponseBadRequest()

        prefix = request.GET.get('prefix')
        while len(codes) < num:
            new_codes = set()
            for i in range(min(num - len(codes), 500)):  # Work around SQLite's SQLITE_MAX_VARIABLE_NUMBER
                new_codes.add(_generate_random_code(prefix=prefix))
            new_codes -= set([v['code'] for v in Voucher.objects.filter(code__in=new_codes).values('code')])
            codes |= new_codes

        return JsonResponse({
            'codes': list(codes)
        })

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
