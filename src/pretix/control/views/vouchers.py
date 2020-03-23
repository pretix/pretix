import io

from defusedcsv import csv
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView, DeleteView, ListView, TemplateView, UpdateView, View,
)

from pretix.base.models import CartPosition, LogEntry, OrderPosition, Voucher
from pretix.base.models.vouchers import _generate_random_code
from pretix.base.services.vouchers import vouchers_send
from pretix.control.forms.filter import VoucherFilterForm, VoucherTagFilterForm
from pretix.control.forms.vouchers import VoucherBulkForm, VoucherForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.signals import voucher_form_class
from pretix.control.views import PaginationMixin
from pretix.helpers.models import modelcopy


class VoucherList(PaginationMixin, EventPermissionRequiredMixin, ListView):
    model = Voucher
    context_object_name = 'vouchers'
    template_name = 'pretixcontrol/vouchers/index.html'
    permission = 'can_view_vouchers'

    def get_queryset(self):
        qs = Voucher.annotate_budget_used_orders(self.request.event.vouchers.filter(
            waitinglistentries__isnull=True
        ).select_related(
            'item', 'variation', 'seat'
        ))
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
            _('Price effect'), _('Value'), _('Tag'), _('Redeemed'), _('Maximum usages'), _('Seat')
        ]
        writer.writerow(headers)

        for v in self.get_queryset():
            if v.item:
                if v.variation:
                    prod = '%s – %s' % (str(v.item), str(v.variation))
                else:
                    prod = '%s' % str(v.item)
            elif v.quota:
                prod = _('Any product in quota "{quota}"').format(quota=str(v.quota.name))
            else:
                prod = _('Any product')
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
                str(v.max_usages),
                str(v.seat) if v.seat else ""
            ]
            writer.writerow(row)

        r = HttpResponse(output.getvalue().encode("utf-8"), content_type='text/csv')
        r['Content-Disposition'] = 'attachment; filename="vouchers.csv"'
        return r


class VoucherTags(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/vouchers/tags.html'
    permission = 'can_view_vouchers'

    def get_queryset(self):
        qs = self.request.event.vouchers.order_by('tag').filter(
            tag__isnull=False,
            waitinglistentries__isnull=True
        )

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        qs = qs.values('tag').annotate(
            total=Sum('max_usages'),
            redeemed=Sum('redeemed')
        )

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        tags = self.get_queryset()

        for t in tags:
            if t['total'] == 0:
                t['percentage'] = 0
            else:
                t['percentage'] = int((t['redeemed'] / t['total']) * 100)

        ctx['tags'] = tags
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return VoucherTagFilterForm(data=self.request.GET, event=self.request.event)


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
            CartPosition.objects.filter(addon_to__voucher=self.object).delete()
            self.object.cartposition_set.all().delete()
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
        ret = super().form_valid(form)
        url = reverse('control:event.voucher', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'voucher': self.object.pk
        })
        messages.success(self.request, mark_safe(_('The new voucher has been created: {code}').format(
            code=format_html('<a href="{url}">{code}</a>', url=url, code=self.object.code)
        )))
        form.instance.log_action('pretix.voucher.added', data=dict(form.cleaned_data), user=self.request.user)
        return ret

    def post(self, request, *args, **kwargs):
        # TODO: Transform this into an asynchronous call?
        with request.event.lock():
            return super().post(request, *args, **kwargs)


class VoucherGo(EventPermissionRequiredMixin, View):
    permission = 'can_view_vouchers'

    def get_voucher(self, code):
        return Voucher.objects.get(code__iexact=code, event=self.request.event)

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code", "").strip()
        try:
            voucher = self.get_voucher(code)
            return redirect('control:event.voucher', event=request.event.slug, organizer=request.event.organizer.slug,
                            voucher=voucher.id)
        except Voucher.DoesNotExist:
            messages.error(request, _('There is no voucher with the given voucher code.'))
            return redirect('control:event.vouchers', event=request.event.slug, organizer=request.event.organizer.slug)


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

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, 'object', None):
            try:
                return self.request.event.vouchers.get(pk=self.request.GET.get("copy_from"))
            except Voucher.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            i.redeemed = 0
            kwargs['instance'] = i
        else:
            kwargs['instance'] = Voucher(event=self.request.event)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        log_entries = []
        objs = form.save(self.request.event)
        voucherids = []
        for v in objs:
            log_entries.append(
                v.log_action('pretix.voucher.added', data=form.cleaned_data, user=self.request.user, save=False)
            )
            voucherids.append(v.pk)
        LogEntry.objects.bulk_create(log_entries)

        if form.cleaned_data['send']:
            vouchers_send.apply_async(kwargs={
                'event': self.request.event.pk,
                'vouchers': voucherids,
                'subject': form.cleaned_data['send_subject'],
                'message': form.cleaned_data['send_message'],
                'recipients': [r._asdict() for r in form.cleaned_data['send_recipients']],
                'user': self.request.user.pk,
            })
            messages.success(self.request, _('The new vouchers have been created and will be sent out shortly.'))
        else:
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


class VoucherBulkAction(EventPermissionRequiredMixin, View):
    permission = 'can_change_vouchers'

    @cached_property
    def objects(self):
        return self.request.event.vouchers.filter(
            id__in=self.request.POST.getlist('voucher')
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete':
            return render(request, 'pretixcontrol/vouchers/delete_bulk.html', {
                'allowed': self.objects.filter(redeemed=0),
                'forbidden': self.objects.exclude(redeemed=0),
            })
        elif request.POST.get('action') == 'delete_confirm':
            for obj in self.objects:
                if obj.allow_delete():
                    obj.log_action('pretix.voucher.deleted', user=self.request.user)
                    OrderPosition.objects.filter(addon_to__voucher=obj).delete()
                    obj.cartposition_set.all().delete()
                    obj.delete()
                else:
                    obj.log_action('pretix.voucher.changed', user=self.request.user, data={
                        'max_usages': min(obj.redeemed, obj.max_usages),
                        'bulk': True
                    })
                    obj.max_usages = min(obj.redeemed, obj.max_usages)
                    obj.save(update_fields=['max_usages'])
            messages.success(request, _('The selected vouchers have been deleted or disabled.'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
