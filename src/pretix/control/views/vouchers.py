from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import resolve, reverse
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponseRedirect
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import (
    CreateView, DeleteView, ListView, TemplateView, UpdateView,
)

from pretix.base.models import Voucher
from pretix.control.forms.vouchers import VoucherBulkForm, VoucherForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.signals import voucher_form_class


class VoucherList(EventPermissionRequiredMixin, ListView):
    model = Voucher
    context_object_name = 'vouchers'
    paginate_by = 30
    template_name = 'pretixcontrol/vouchers/index.html'
    permission = 'can_change_vouchers'

    def get_queryset(self):
        qs = self.request.event.vouchers.all().select_related('item')
        if self.request.GET.get("search", "") != "":
            s = self.request.GET.get("search", "")
            qs = qs.filter(Q(code__icontains=s) | Q(tag__icontains=s) | Q(comment__icontains=s))
        if self.request.GET.get("tag", "") != "":
            s = self.request.GET.get("tag", "")
            qs = qs.filter(tag=s)
        if self.request.GET.get("status", "") != "":
            s = self.request.GET.get("status", "")
            if s == 'v':
                qs = qs.filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now())).filter(redeemed=False)
            elif s == 'r':
                qs = qs.filter(redeemed=True)
            elif s == 'e':
                qs = qs.filter(Q(valid_until__isnull=False) & Q(valid_until__lt=now())).filter(redeemed=False)
        return qs


class VoucherTags(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/vouchers/tags.html'
    permission = 'can_change_vouchers'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        tags = self.request.event.vouchers.order_by().filter(tag__isnull=False).values('tag').annotate(
            total=Count('id'),
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
        if self.get_object().is_ordered():
            messages.error(request, _('A voucher can not be deleted if it already has been redeemed.'))
            return HttpResponseRedirect(self.get_success_url())
        return super().get(request, *args, **kwargs)

    @transaction.atomic()
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        if self.object.is_ordered():
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

    @transaction.atomic()
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

    @transaction.atomic()
    def form_valid(self, form):
        form.instance.event = self.request.event
        messages.success(self.request, _('The new voucher has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.voucher.added', data=dict(form.cleaned_data), user=self.request.user)
        return ret


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

    @transaction.atomic()
    def form_valid(self, form):
        for o in form.save(self.request.event):
            o.log_action('pretix.voucher.added', data=form.cleaned_data, user=self.request.user)
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
