from django.contrib import messages
from django.core.urlresolvers import resolve, reverse
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

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
        return qs


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
