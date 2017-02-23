from datetime import timedelta

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView, ListView, TemplateView, View

from pretix.base.i18n import language
from pretix.base.models import (
    CachedFile, CachedTicket, Invoice, InvoiceAddress, Item, ItemVariation,
    Order, Quota, generate_position_secret, generate_secret,
)
from pretix.base.services.export import export
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_pdf, invoice_qualified,
    regenerate_invoice,
)
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException, mail
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, cancel_order, mark_order_paid,
)
from pretix.base.services.stats import order_overview
from pretix.base.signals import (
    register_data_exporters, register_payment_providers,
)
from pretix.control.forms.orders import (
    CommentForm, ExporterForm, ExtendForm, OrderContactForm,
    OrderPositionChangeForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.multidomain.urlreverse import build_absolute_uri


class OrderList(EventPermissionRequiredMixin, ListView):
    model = Order
    context_object_name = 'orders'
    paginate_by = 30
    template_name = 'pretixcontrol/orders/index.html'
    permission = 'can_view_orders'

    def get_queryset(self):
        qs = Order.objects.filter(
            event=self.request.event
        )
        if self.request.GET.get("user", "") != "":
            u = self.request.GET.get("user", "")
            qs = qs.filter(
                Q(email__icontains=u) | Q(positions__attendee_name__icontains=u)
            )
        if self.request.GET.get("status", "") != "":
            s = self.request.GET.get("status", "")
            if s == 'o':
                qs = qs.filter(status=Order.STATUS_PENDING, expires__lt=now().replace(hour=0, minute=0, second=0))
            elif s == 'ne':
                qs = qs.filter(status__in=[Order.STATUS_PENDING, Order.STATUS_EXPIRED])
            else:
                qs = qs.filter(status=s)
        if self.request.GET.get("item", "") != "":
            i = self.request.GET.get("item", "")
            qs = qs.filter(positions__item_id__in=(i,))
        if self.request.GET.get("provider", "") != "":
            p = self.request.GET.get("provider", "")
            qs = qs.filter(payment_provider=p)
        if self.request.GET.get("ordering", "") != "":
            p = self.request.GET.get("ordering", "")
            p_admissable = ('-code', 'code', '-email', 'email', '-total', 'total', '-datetime', 'datetime', '-status', 'status')
            if p in p_admissable:
                qs = qs.order_by(p)

        return qs.distinct()

    def get_payment_providers(self):
        providers = []
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            providers.append({
                'name': provider.identifier,
                'verbose_name': provider.verbose_name
            })
        return providers

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = Item.objects.filter(event=self.request.event)
        ctx['filtered'] = ("status" in self.request.GET or "item" in self.request.GET or "user" in self.request.GET or "provider" in self.request.GET)
        ctx['providers'] = self.get_payment_providers()
        return ctx


class OrderView(EventPermissionRequiredMixin, DetailView):
    context_object_name = 'order'
    model = Order

    def get_object(self, queryset=None):
        try:
            return Order.objects.get(
                event=self.request.event,
                code=self.kwargs['code'].upper()
            )
        except Order.DoesNotExist:
            raise Http404()

    def _redirect_back(self):
        return redirect('control:event.order',
                        event=self.request.event.slug,
                        organizer=self.request.event.organizer.slug,
                        code=self.order.code)

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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.get_items()
        ctx['event'] = self.request.event
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
            'item__questions', 'answers', 'answers__question', 'checkins'
        ).order_by('positionid')

        positions = []
        for p in cartpos:
            p.has_questions = (
                (p.item.admission and self.request.event.settings.attendee_names_asked) or
                p.item.questions.all()
            )
            p.cache_answers()
            positions.append(p)

        return {
            'positions': positions,
            'raw': cartpos,
            'total': self.object.total,
            'payment_fee': self.object.payment_fee,
            'net_total': self.object.net_total,
            'tax_total': self.object.tax_total,
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

    def get(self, *args, **kwargs):
        return HttpResponseNotAllowed(['POST'])


class OrderTransition(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        to = self.request.POST.get('status', '')
        if self.order.status in (Order.STATUS_PENDING, Order.STATUS_EXPIRED) and to == 'p':
            try:
                mark_order_paid(self.order, manual=True, user=self.request.user)
            except Quota.QuotaExceededException as e:
                messages.error(self.request, str(e))
            except SendMailException:
                messages.warning(self.request, _('The order has been marked as paid, but we were unable to send a confirmation mail.'))
            else:
                messages.success(self.request, _('The order has been marked as paid.'))
        elif self.order.status == Order.STATUS_PENDING and to == 'c':
            cancel_order(self.order, user=self.request.user)
            messages.success(self.request, _('The order has been canceled.'))
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
        except Invoice.DoesNotExist:
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

    def get(self, *args, **kwargs):  # NOQA
        return HttpResponseNotAllowed(['POST'])


class OrderInvoiceReissue(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        try:
            inv = self.order.invoices.get(pk=kwargs.get('id'))
        except Invoice.DoesNotExist:
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

    def get(self, *args, **kwargs):  # NOQA
        return HttpResponseNotAllowed(['POST'])


class OrderResendLink(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        with language(self.order.locale):
            try:
                try:
                    invoice_name = self.order.invoice_address.name
                    invoice_company = self.order.invoice_address.company
                except InvoiceAddress.DoesNotExist:
                    invoice_name = ""
                    invoice_company = ""
                mail(
                    self.order.email, _('Your order: %(code)s') % {'code': self.order.code},
                    self.order.event.settings.mail_text_resend_link,
                    {
                        'event': self.order.event.name,
                        'url': build_absolute_uri(self.order.event, 'presale:event.order', kwargs={
                            'order': self.order.code,
                            'secret': self.order.secret
                        }),
                        'invoice_name': invoice_name,
                        'invoice_company': invoice_company,
                    },
                    self.order.event, locale=self.order.locale
                )
            except SendMailException:
                messages.error(self.request, _('There was an error sending the mail. Please try again later.'))
                return redirect(self.get_order_url())

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

        resp = FileResponse(self.invoice.file.file, content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="{}.pdf"'.format(self.invoice.number)
        return resp


class OrderExtend(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if self.form.is_valid():
            if self.order.status == Order.STATUS_PENDING:
                messages.success(self.request, _('The payment term has been changed.'))
                self.order.log_action('pretix.event.order.expirychanged', user=self.request.user, data={
                    'expires': self.order.expires,
                    'state_change': False
                })
                self.form.save()
            else:
                try:
                    with self.order.event.lock() as now_dt:
                        is_available = self.order._is_still_available(now_dt)
                        if is_available is True:
                            self.form.save()
                            self.order.status = Order.STATUS_PENDING
                            self.order.save()
                            self.order.log_action('pretix.event.order.expirychanged', user=self.request.user, data={
                                'expires': self.order.expires,
                                'state_change': True
                            })
                            messages.success(self.request, _('The payment term has been changed.'))
                        else:
                            messages.error(self.request, is_available)
                except LockTimeoutException:
                    messages.error(self.request, _('We were not able to process the request completely as the '
                                                   'server was too busy.'))
            return self._redirect_back()
        else:
            return self.get(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            messages.error(self.request, _('This action is only allowed for pending orders.'))
            return self._redirect_back()
        return super().dispatch(request, *kwargs, **kwargs)

    def get(self, *args, **kwargs):
        return render(self.request, 'pretixcontrol/order/extend.html', {
            'order': self.order,
            'form': self.form,
        })

    @cached_property
    def form(self):
        return ExtendForm(instance=self.order,
                          data=self.request.POST if self.request.method == "POST" else None)


class OrderChange(OrderView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/order/change.html'

    def dispatch(self, request, *args, **kwargs):
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_PAID):
            messages.error(self.request, _('This action is only allowed for pending or paid orders.'))
            return self._redirect_back()
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def positions(self):
        positions = list(self.order.positions.all())
        for p in positions:
            p.form = OrderPositionChangeForm(prefix='op-{}'.format(p.pk), instance=p,
                                             data=self.request.POST if self.request.method == "POST" else None)
        return positions

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['positions'] = self.positions
        return ctx

    def post(self, *args, **kwargs):
        ocm = OrderChangeManager(self.order, self.request.user)
        form_valid = True
        for p in self.positions:
            if not p.form.is_valid():
                form_valid = False
                break

            try:
                if p.form.cleaned_data['operation'] == 'product':
                    if '-' in p.form.cleaned_data['itemvar']:
                        itemid, varid = p.form.cleaned_data['itemvar'].split('-')
                    else:
                        itemid, varid = p.form.cleaned_data['itemvar'], None

                    item = Item.objects.get(pk=itemid, event=self.request.event)
                    if varid:
                        variation = ItemVariation.objects.get(pk=varid, item=item)
                    else:
                        variation = None
                    ocm.change_item(p, item, variation)
                elif p.form.cleaned_data['operation'] == 'price':
                    ocm.change_price(p, p.form.cleaned_data['price'])
                elif p.form.cleaned_data['operation'] == 'cancel':
                    ocm.cancel(p)

            except OrderError as e:
                p.custom_error = str(e)
                form_valid = False
                break

        if not form_valid:
            messages.error(self.request, _('An error occured. Please see the details below.'))
        else:
            try:
                ocm.commit()
            except OrderError as e:
                messages.error(self.request, str(e))
            else:
                messages.success(self.request, _('The order has been changed and the user has been notified.'))
                return self._redirect_back()

        return self.get(*args, **kwargs)


class OrderContactChange(OrderView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/order/change_contact.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['form'] = self.form
        return ctx

    @cached_property
    def form(self):
        return OrderContactForm(
            instance=self.order,
            data=self.request.POST if self.request.method == "POST" else None
        )

    def post(self, *args, **kwargs):
        old_email = self.order.email
        if self.form.is_valid():
            self.order.log_action(
                'pretix.event.order.contact.changed',
                data={
                    'old_email': old_email,
                    'new_email': self.form.cleaned_data['email'],
                },
                user=self.request.user,
            )
            if self.form.cleaned_data['regenerate_secrets']:
                self.order.secret = generate_secret()
                for op in self.order.positions.all():
                    op.secret = generate_position_secret()
                    op.save()
                CachedTicket.objects.filter(order_position__order=self.order).delete()
                self.order.log_action('pretix.event.order.secret.changed', user=self.request.user)

            self.form.save()
            messages.success(self.request, _('The order has been changed.'))
            return redirect(self.get_order_url())
        return self.get(*args, **kwargs)


class OverView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/orders/overview.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['items_by_category'], ctx['total'] = order_overview(self.request.event)
        return ctx


class OrderGo(EventPermissionRequiredMixin, View):
    permission = 'can_view_orders'

    def get_order(self, code):
        try:
            return Order.objects.get(code=code, event=self.request.event)
        except Order.DoesNotExist:
            return Order.objects.get(code=Order.normalize_code(code), event=self.request.event)

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code", "").upper().strip()
        try:
            if code.startswith(request.event.slug.upper()):
                code = code[len(request.event.slug):]
            if code.startswith('-'):
                code = code[1:]
            order = self.get_order(code)
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
                data=(self.request.POST if self.request.method == 'POST' else None),
                prefix=ex.identifier
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
        export.apply_async(args=(self.request.event.id, str(cf.id), self.exporter.identifier,
                                 self.exporter.form.cleaned_data))
        return redirect(reverse('cachedfile.download', kwargs={'id': str(cf.id)}))
