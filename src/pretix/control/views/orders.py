from datetime import timedelta
from itertools import groupby

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView, View

from pretix.base.i18n import language
from pretix.base.models import (
    CachedFile, CachedTicket, EventLock, Invoice, Item, Order, Quota,
)
from pretix.base.services import tickets
from pretix.base.services.export import export
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_pdf, invoice_qualified,
    regenerate_invoice,
)
from pretix.base.services.mail import mail
from pretix.base.services.orders import cancel_order, mark_order_paid
from pretix.base.services.stats import order_overview
from pretix.base.signals import (
    register_data_exporters, register_payment_providers,
    register_ticket_outputs,
)
from pretix.control.forms.orders import CommentForm, ExporterForm, ExtendForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.multidomain.urlreverse import build_absolute_uri


class OrderList(EventPermissionRequiredMixin, ListView):
    model = Order
    context_object_name = 'orders'
    template_name = 'pretixcontrol/orders/index.html'
    paginate_by = 30
    permission = 'can_view_orders'

    def get_queryset(self):
        qs = Order.objects.filter(
            event=self.request.event
        )
        if self.request.GET.get("user", "") != "":
            u = self.request.GET.get("user", "")
            qs = qs.filter(
                Q(email__icontains=u)
            )
        if self.request.GET.get("status", "") != "":
            s = self.request.GET.get("status", "")
            if s == 'o':
                qs = qs.filter(status=Order.STATUS_PENDING, expires__lt=now())
            else:
                qs = qs.filter(status=s)
        if self.request.GET.get("item", "") != "":
            i = self.request.GET.get("item", "")
            qs = qs.filter(positions__item_id__in=(i,)).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = Item.objects.filter(event=self.request.event)
        ctx['filtered'] = ("status" in self.request.GET or "item" in self.request.GET or "user" in self.request.GET)
        return ctx


class OrderView(EventPermissionRequiredMixin, DetailView):
    context_object_name = 'order'
    model = Order

    def get_object(self, queryset=None):
        return Order.objects.get(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        )

    @cached_property
    def order(self):
        return self.get_object()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['can_generate_invoice'] = invoice_qualified(self.order) and (
            self.request.event.settings.invoice_generate == 'admin' or
            self.request.event.settings.invoice_generate == 'user'
        )
        return ctx

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.order.payment_provider:
                return provider

    def get_order_url(self):
        return reverse('control:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'code': self.order.code
        })


class OrderDetail(OrderView):
    template_name = 'pretixcontrol/order/index.html'
    permission = 'can_view_orders'

    @cached_property
    def download_buttons(self):
        buttons = []
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if not provider.is_enabled:
                continue
            buttons.append({
                'icon': provider.download_button_icon or 'fa-download',
                'text': provider.download_button_text or 'fa-download',
                'identifier': provider.identifier,
            })
        return buttons

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.get_items()
        ctx['event'] = self.request.event
        ctx['download_buttons'] = self.download_buttons
        ctx['can_download'] = (
            self.request.event.settings.ticket_download
            and self.order.status == Order.STATUS_PAID
        )
        ctx['payment'] = self.payment_provider.order_control_render(self.request, self.object)
        ctx['invoices'] = list(self.order.invoices.all().select_related('event'))
        ctx['comment_form'] = CommentForm(initial={'comment': self.order.comment})
        return ctx

    def get_items(self):
        queryset = self.object.positions.all()

        cartpos = queryset.order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            'item__questions', 'answers', 'answers__question'
        )

        # Group items of the same variation
        # We do this by list manipulations instead of a GROUP BY query, as
        # Django is unable to join related models in a .values() query
        def keyfunc(pos):
            if (pos.item.admission and self.request.event.settings.attendee_names_asked) \
                    or pos.item.questions.all():
                return pos.id, 0, 0, 0, 0, 0
            return 0, pos.item_id, pos.variation_id, pos.price, pos.tax_rate, (pos.voucher_id or 0)

        positions = []
        for k, g in groupby(sorted(list(cartpos), key=keyfunc), key=keyfunc):
            g = list(g)
            group = g[0]
            group.count = len(g)
            group.total = group.count * group.price
            group.has_questions = k[0] != ""
            group.cache_answers()
            positions.append(group)

        return {
            'positions': positions,
            'raw': cartpos,
            'total': self.object.total,
            'payment_fee': self.object.payment_fee,
        }


class OrderComment(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        form = CommentForm(self.request.POST)
        if form.is_valid():
            self.order.comment = form.cleaned_data.get('comment')
            self.order.save()
            self.order.log_action('pretix.event.order.comment', user=self.request.user)
            messages.success(self.request, _('The comment has been updated.'))
        else:
            messages.error(self.request, _('Could not update the comment.'))
        return redirect(self.get_order_url())


class OrderTransition(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        to = self.request.POST.get('status', '')
        if self.order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and to == 'p':
            try:
                mark_order_paid(self.order, manual=True, user=self.request.user)
            except Quota.QuotaExceededException as e:
                messages.error(self.request, str(e))
            else:
                messages.success(self.request, _('The order has been marked as paid.'))
        elif self.order.status == Order.STATUS_PENDING and to == 'c':
            cancel_order(self.order, user=self.request.user)
            messages.success(self.request, _('The order has been cancelled.'))
        elif self.order.status == Order.STATUS_PAID and to == 'n':
            self.order.status = Order.STATUS_PENDING
            self.order.payment_manual = True
            self.order.save()
            self.order.log_action('pretix.event.order.unpaid', user=self.request.user)
            messages.success(self.request, _('The order has been marked as not paid.'))
        elif self.order.status == Order.STATUS_PENDING and to == 'e':
            self.order.status = Order.STATUS_EXPIRED
            self.order.save()
            self.order.log_action('pretix.event.order.expired', user=self.request.user)
            messages.success(self.request, _('The order has been marked as expired.'))
        elif self.order.status == Order.STATUS_PAID and to == 'r':
            ret = self.payment_provider.order_control_refund_perform(self.request, self.order)
            if ret:
                return redirect(ret)
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        to = self.request.GET.get('status', '')
        if self.order.status == Order.STATUS_PENDING and to == 'c':
            return render(self.request, 'pretixcontrol/order/cancel.html', {
                'order': self.order,
            })
        elif self.order.status == Order.STATUS_PAID and to == 'r':
            return render(self.request, 'pretixcontrol/order/refund.html', {
                'order': self.order,
                'payment': self.payment_provider.order_control_refund_render(self.order),
            })
        else:
            return HttpResponseNotAllowed(['POST'])


class OrderInvoiceCreate(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if self.request.event.settings.get('invoice_generate') not in ('admin', 'user') or not invoice_qualified(
                self.order):
            messages.error(self.request, _('You cannot generate an invoice for this order.'))
        elif self.order.invoices.exists():
            messages.error(self.request, _('An invoice for this order already exists.'))
        else:
            inv = generate_invoice(self.order)
            self.order.log_action('pretix.event.order.invoice.generated', user=self.request.user, data={
                'invoice': inv.pk
            })
            messages.success(self.request, _('The invoice has been generated.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class OrderInvoiceRegenerate(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        try:
            inv = self.order.invoices.get(pk=kwargs.get('id'))
        except Order.DoesNotExist:
            messages.error(self.request, _('Unknown invoice.'))
        else:
            if inv.canceled:
                messages.error(self.request, _('The invoice has already been canceled.'))
            else:
                inv = regenerate_invoice(inv)
                self.order.log_action('pretix.event.order.invoice.regenerated', user=self.request.user, data={
                    'invoice': inv.pk
                })
                messages.success(self.request, _('The invoice has been regenerated.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class OrderInvoiceReissue(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        try:
            inv = self.order.invoices.get(pk=kwargs.get('id'))
        except Order.DoesNotExist:
            messages.error(self.request, _('Unknown invoice.'))
        else:
            if inv.canceled:
                messages.error(self.request, _('The invoice has already been canceled.'))
            else:
                generate_cancellation(inv)
                inv = generate_invoice(self.order)
                self.order.log_action('pretix.event.order.invoice.reissued', user=self.request.user, data={
                    'invoice': inv.pk
                })
                messages.success(self.request, _('The invoice has been reissued.'))
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class OrderResendLink(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        with language(self.order.locale):
            mail(
                self.order.email, _('Your order: %(code)s') % {'code': self.order.code},
                self.order.event.settings.mail_text_resend_link,
                {
                    'event': self.order.event.name,
                    'url': build_absolute_uri(self.order.event, 'presale:event.order', kwargs={
                        'order': self.order.code,
                        'secret': self.order.secret
                    }),
                },
                self.order.event, locale=self.order.locale
            )
        messages.success(self.request, _('The email has been queued to be sent.'))
        self.order.log_action('pretix.event.order.resend', user=self.request.user)
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class InvoiceDownload(EventPermissionRequiredMixin, View):
    permission = 'can_view_orders'

    def get_order_url(self):
        return reverse('control:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'code': self.invoice.order.code
        })

    def get(self, request, *args, **kwargs):
        try:
            self.invoice = Invoice.objects.get(
                event=self.request.event,
                id=self.kwargs['invoice']
            )
        except Invoice.DoesNotExist:
            raise Http404(_('This invoice has not been found'))

        if not self.invoice.file:
            invoice_pdf(self.invoice.pk)
            self.invoice = Invoice.objects.get(pk=self.invoice.pk)

        if not self.invoice.file:
            # This happens if we have celery installed and the file will be generated in the background
            messages.warning(request, _('The invoice file has not yet been generated, we will generate it for you '
                                        'now. Please try again in a few seconds.'))
            return redirect(self.get_order_url())

        return redirect(self.invoice.file.url)


class OrderDownload(OrderView):

    @cached_property
    def output(self):
        responses = register_ticket_outputs.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.kwargs.get('output'):
                return provider

    def get(self, request, *args, **kwargs):
        if not self.output or not self.output.is_enabled:
            messages.error(request, _('You requested an invalid ticket output type.'))
            return redirect(self.get_order_url())
        if self.order.status != Order.STATUS_PAID:
            messages.error(request, _('Order is not paid.'))
            return redirect(self.get_order_url())

        try:
            ct = CachedTicket.objects.get(order=self.order, provider=self.output.identifier)
        except CachedTicket.DoesNotExist:
            ct = CachedTicket(order=self.order, provider=self.output.identifier)
        try:
            ct.cachedfile
        except CachedFile.DoesNotExist:
            cf = CachedFile()
            cf.date = now()
            cf.expires = self.request.event.date_from + timedelta(days=30)
            cf.save()
            ct.cachedfile = cf
        ct.save()
        if not ct.cachedfile.file.name:
            tickets.generate(self.order.id, self.output.identifier)
        return redirect(reverse('cachedfile.download', kwargs={'id': ct.cachedfile.id}))


class OrderExtend(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if self.order.status != Order.STATUS_PENDING:
            messages.error(self.request, _('This action is only allowed for pending orders.'))
            return self._redirect_back()
        oldvalue = self.order.expires

        if self.form.is_valid():
            if oldvalue > now():
                messages.success(self.request, _('The payment term has been changed.'))
                self.order.log_action('pretix.event.order.expirychanged', user=self.request.user, data={
                    'expires': self.order.expires
                })
                self.form.save()
            else:
                try:
                    with self.order.event.lock():
                        is_available = self.order._is_still_available()
                        if is_available is True:
                            self.form.save()
                            self.order.log_action('pretix.event.order.expirychanged', user=self.request.user, data={
                                'expires': self.order.expires
                            })
                            messages.success(self.request, _('The payment term has been changed.'))
                        else:
                            messages.error(self.request, is_available)
                except EventLock.LockTimeoutException:
                    messages.error(self.request, _('We were not able to process the request completely as the '
                                                   'server was too busy.'))
            return self._redirect_back()
        else:
            return self.get(*args, **kwargs)

    def _redirect_back(self):
        return redirect('control:event.order',
                        event=self.request.event.slug,
                        organizer=self.request.event.organizer.slug,
                        code=self.order.code)

    def get(self, *args, **kwargs):
        if self.order.status != Order.STATUS_PENDING:
            messages.error(self.request, _('This action is only allowed for pending orders.'))
            return self._redirect_back()
        return render(self.request, 'pretixcontrol/order/extend.html', {
            'order': self.order,
            'form': self.form,
        })

    @cached_property
    def form(self):
        return ExtendForm(instance=self.order,
                          data=self.request.POST if self.request.method == "POST" else None)


class OverView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/orders/overview.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['items_by_category'], ctx['total'] = order_overview(self.request.event)
        return ctx


class OrderGo(EventPermissionRequiredMixin, View):
    permission = 'can_view_orders'

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code", "").upper().strip()
        try:
            if code.startswith(request.event.slug.upper()):
                code = code[len(request.event.slug.upper()):]
            order = Order.objects.get(code=code, event=request.event)
            return redirect('control:event.order', event=request.event.slug, organizer=request.event.organizer.slug,
                            code=order.code)
        except Order.DoesNotExist:
            messages.error(request, _('There is no order with the given order code.'))
            return redirect('control:event.orders', event=request.event.slug, organizer=request.event.organizer.slug)


class ExportView(EventPermissionRequiredMixin, TemplateView):
    permission = 'can_view_orders'
    template_name = 'pretixcontrol/orders/export.html'

    @cached_property
    def exporters(self):
        exporters = []
        responses = register_data_exporters.send(self.request.event)
        for receiver, response in responses:
            ex = response(self.request.event)
            ex.form = ExporterForm(
                data=(self.request.POST if self.request.method == 'POST' else None)
            )
            ex.form.fields = ex.export_form_fields
            exporters.append(ex)
        return exporters

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['exporters'] = self.exporters
        return ctx

    @cached_property
    def exporter(self):
        for ex in self.exporters:
            if ex.identifier == self.request.POST.get("exporter"):
                return ex

    def post(self, *args, **kwargs):
        if not self.exporter:
            messages.error(self.request, _('The selected exporter was not found.'))
            return redirect('control:event.orders.export', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            })
        if not self.exporter.form.is_valid():
            messages.error(self.request, _('There was a problem processing your input. See below for error details.'))
            return self.get(*args, **kwargs)

        cf = CachedFile()
        cf.date = now()
        cf.expires = now() + timedelta(days=3)
        cf.save()
        export(self.request.event.id, str(cf.id), self.exporter.identifier, self.exporter.form.cleaned_data)
        return redirect(reverse('cachedfile.download', kwargs={'id': str(cf.id)}))
