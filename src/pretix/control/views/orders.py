import logging
import mimetypes
import os
from datetime import timedelta

import pytz
import vat_moss.id
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.formats import date_format
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic import (
    DetailView, FormView, ListView, TemplateView, View,
)
from i18nfield.strings import LazyI18nString

from pretix.base.i18n import language
from pretix.base.models import (
    CachedCombinedTicket, CachedFile, CachedTicket, Invoice, InvoiceAddress,
    Item, ItemVariation, LogEntry, Order, QuestionAnswer, Quota,
    generate_position_secret, generate_secret,
)
from pretix.base.models.event import SubEvent
from pretix.base.models.orders import OrderFee
from pretix.base.models.tax import EU_COUNTRIES
from pretix.base.services.export import export
from pretix.base.services.invoices import (
    generate_cancellation, generate_invoice, invoice_pdf, invoice_qualified,
    regenerate_invoice,
)
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException, render_mail
from pretix.base.services.orders import (
    OrderChangeManager, OrderError, cancel_order, extend_order,
    mark_order_expired, mark_order_paid,
)
from pretix.base.services.stats import order_overview
from pretix.base.signals import register_data_exporters
from pretix.base.views.async import AsyncAction
from pretix.base.views.mixins import OrderQuestionsViewMixin
from pretix.control.forms.filter import EventOrderFilterForm
from pretix.control.forms.orders import (
    CommentForm, ExporterForm, ExtendForm, OrderContactForm, OrderLocaleForm,
    OrderMailForm, OrderPositionAddForm, OrderPositionChangeForm,
    OtherOperationsForm,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import PaginationMixin
from pretix.helpers.safedownload import check_token
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.presale.signals import question_form_fields

logger = logging.getLogger(__name__)


class OrderList(EventPermissionRequiredMixin, PaginationMixin, ListView):
    model = Order
    context_object_name = 'orders'
    template_name = 'pretixcontrol/orders/index.html'
    permission = 'can_view_orders'

    def get_queryset(self):
        qs = Order.objects.filter(
            event=self.request.event
        ).annotate(pcnt=Count('positions', distinct=True)).select_related('invoice_address')
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return EventOrderFilterForm(data=self.request.GET, event=self.request.event)


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
            self.request.event.settings.invoice_generate in ('admin', 'user', 'paid', 'True')
        )
        return ctx

    @cached_property
    def payment_provider(self):
        return self.request.event.get_payment_providers().get(self.order.payment_provider)

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
        ctx['comment_form'] = CommentForm(initial={
            'comment': self.order.comment,
            'checkin_attention': self.order.checkin_attention
        })
        ctx['display_locale'] = dict(settings.LANGUAGES)[self.object.locale or self.request.event.settings.locale]
        return ctx

    def get_items(self):
        queryset = self.object.positions.all()

        cartpos = queryset.order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation', 'addon_to', 'tax_rule'
        ).prefetch_related(
            'item__questions', 'answers', 'answers__question', 'checkins', 'checkins__list'
        ).order_by('positionid')

        positions = []
        for p in cartpos:
            responses = question_form_fields.send(sender=self.request.event, position=p)
            p.additional_fields = []
            data = p.meta_info_data
            for r, response in sorted(responses, key=lambda r: str(r[0])):
                for key, value in response.items():
                    p.additional_fields.append({
                        'answer': data.get('question_form_data', {}).get(key),
                        'question': value.label
                    })

            p.has_questions = (
                p.additional_fields or
                (p.item.admission and self.request.event.settings.attendee_names_asked) or
                (p.item.admission and self.request.event.settings.attendee_emails_asked) or
                p.item.questions.all()
            )
            p.cache_answers()

            positions.append(p)

        positions.sort(key=lambda p: p.sort_key)

        return {
            'positions': positions,
            'raw': cartpos,
            'total': self.object.total,
            'fees': self.object.fees.all(),
            'net_total': self.object.net_total,
            'tax_total': self.object.tax_total,
        }


class OrderComment(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        form = CommentForm(self.request.POST)
        if form.is_valid():
            if form.cleaned_data.get('comment') != self.order.comment:
                self.order.comment = form.cleaned_data.get('comment')
                self.order.log_action('pretix.event.order.comment', user=self.request.user, data={
                    'new_comment': form.cleaned_data.get('comment')
                })

            if form.cleaned_data.get('checkin_attention') != self.order.checkin_attention:
                self.order.checkin_attention = form.cleaned_data.get('checkin_attention')
                self.order.log_action('pretix.event.order.checkin_attention', user=self.request.user, data={
                    'new_value': form.cleaned_data.get('checkin_attention')
                })
            self.order.save()
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
                mark_order_paid(self.order, manual=True, user=self.request.user,
                                count_waitinglist=False)
            except Quota.QuotaExceededException as e:
                messages.error(self.request, str(e))
            except SendMailException:
                messages.warning(self.request, _('The order has been marked as paid, but we were unable to send a confirmation mail.'))
            else:
                messages.success(self.request, _('The order has been marked as paid.'))
        elif self.order.cancel_allowed() and to == 'c':
            cancel_order(self.order, user=self.request.user, send_mail=self.request.POST.get("send_email") == "on")
            messages.success(self.request, _('The order has been canceled.'))
        elif self.order.status == Order.STATUS_PAID and to == 'n':
            self.order.status = Order.STATUS_PENDING
            self.order.payment_manual = True
            self.order.save()
            self.order.log_action('pretix.event.order.unpaid', user=self.request.user)
            messages.success(self.request, _('The order has been marked as not paid.'))
        elif self.order.status == Order.STATUS_PENDING and to == 'e':
            mark_order_expired(self.order, user=self.request.user)
            messages.success(self.request, _('The order has been marked as expired.'))
        elif self.order.status == Order.STATUS_PAID and to == 'r':
            ret = self.payment_provider.order_control_refund_perform(self.request, self.order)
            if ret:
                return redirect(ret)
        return redirect(self.get_order_url())

    def get(self, *args, **kwargs):
        to = self.request.GET.get('status', '')
        if self.order.cancel_allowed() and to == 'c':
            return render(self.request, 'pretixcontrol/order/cancel.html', {
                'order': self.order,
            })
        elif self.order.status == Order.STATUS_PAID and to == 'r':
            try:
                cr = self.payment_provider.order_control_refund_render(self.order, self.request)
            except TypeError:
                cr = self.payment_provider.order_control_refund_render(self.order)

            return render(self.request, 'pretixcontrol/order/refund.html', {
                'order': self.order,
                'payment': cr,
            })
        else:
            return HttpResponseNotAllowed(['POST'])


class OrderInvoiceCreate(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        if self.request.event.settings.get('invoice_generate') not in ('admin', 'user', 'paid') or not invoice_qualified(self.order):
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


class OrderCheckVATID(OrderView):
    permission = 'can_change_orders'

    def post(self, *args, **kwargs):
        try:
            ia = self.order.invoice_address
        except InvoiceAddress.DoesNotExist:
            messages.error(self.request, _('No VAT ID specified.'))
            return redirect(self.get_order_url())
        else:
            if not ia.vat_id:
                messages.error(self.request, _('No VAT ID specified.'))
                return redirect(self.get_order_url())

            if not ia.country:
                messages.error(self.request, _('No country specified.'))
                return redirect(self.get_order_url())

            if str(ia.country) not in EU_COUNTRIES:
                messages.error(self.request, _('VAT ID could not be checked since a non-EU country has been '
                                               'specified.'))
                return redirect(self.get_order_url())

            if ia.vat_id[:2] != str(ia.country):
                messages.error(self.request, _('Your VAT ID does not match the selected country.'))
                return redirect(self.get_order_url())

            try:
                result = vat_moss.id.validate(ia.vat_id)
                if result:
                    country_code, normalized_id, company_name = result
                    ia.vat_id_validated = True
                    ia.vat_id = normalized_id
                    ia.save()
            except vat_moss.errors.InvalidError:
                messages.error(self.request, _('This VAT ID is not valid.'))
            except vat_moss.errors.WebServiceUnavailableError:
                logger.exception('VAT ID checking failed for country {}'.format(ia.country))
                messages.error(self.request, _('The VAT ID could not be checked, as the VAT checking service of '
                                               'the country is currently not available.'))
            else:
                messages.success(self.request, _('This VAT ID is valid.'))
            return redirect(self.get_order_url())

    def get(self, *args, **kwargs):  # NOQA
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
                c = generate_cancellation(inv)
                if self.order.status not in (Order.STATUS_CANCELED, Order.STATUS_REFUNDED):
                    inv = generate_invoice(self.order)
                else:
                    inv = c
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
                email_template = self.order.event.settings.mail_text_resend_link
                email_context = {
                    'event': self.order.event.name,
                    'url': build_absolute_uri(self.order.event, 'presale:event.order', kwargs={
                        'order': self.order.code,
                        'secret': self.order.secret
                    }),
                    'invoice_name': invoice_name,
                    'invoice_company': invoice_company,
                }
                email_subject = _('Your order: %(code)s') % {'code': self.order.code}
                self.order.send_mail(
                    email_subject, email_template, email_context,
                    'pretix.event.order.email.resend', user=self.request.user
                )
            except SendMailException:
                messages.error(self.request, _('There was an error sending the mail. Please try again later.'))
                return redirect(self.get_order_url())

        messages.success(self.request, _('The email has been queued to be sent.'))
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
            try:
                extend_order(
                    self.order,
                    new_date=self.form.cleaned_data.get('expires'),
                    force=self.form.cleaned_data.get('quota_ignore', False),
                    user=self.request.user
                )
                messages.success(self.request, _('The payment term has been changed.'))
            except OrderError as e:
                messages.error(self.request, str(e))
                return self._redirect_here()
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

    def _redirect_here(self):
        return redirect('control:event.order.extend',
                        event=self.request.event.slug,
                        organizer=self.request.event.organizer.slug,
                        code=self.order.code)

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
    def other_form(self):
        return OtherOperationsForm(prefix='other', order=self.order,
                                   data=self.request.POST if self.request.method == "POST" else None)

    @cached_property
    def add_form(self):
        return OrderPositionAddForm(prefix='add', order=self.order,
                                    data=self.request.POST if self.request.method == "POST" else None)

    @cached_property
    def positions(self):
        positions = list(self.order.positions.all())
        for p in positions:
            p.form = OrderPositionChangeForm(prefix='op-{}'.format(p.pk), instance=p,
                                             data=self.request.POST if self.request.method == "POST" else None)
            try:
                ia = self.order.invoice_address
            except InvoiceAddress.DoesNotExist:
                ia = None
            p.apply_tax = p.item.tax_rule and p.item.tax_rule.tax_applicable(invoice_address=ia)
        return positions

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['positions'] = self.positions
        ctx['add_form'] = self.add_form
        ctx['other_form'] = self.other_form
        return ctx

    def _process_other(self, ocm):
        if not self.other_form.is_valid():
            return False
        else:
            if self.other_form.cleaned_data['recalculate_taxes']:
                ocm.recalculate_taxes()
            return True

    def _process_add(self, ocm):
        if not self.add_form.is_valid():
            return False
        else:
            if self.add_form.cleaned_data['do']:
                if '-' in self.add_form.cleaned_data['itemvar']:
                    itemid, varid = self.add_form.cleaned_data['itemvar'].split('-')
                else:
                    itemid, varid = self.add_form.cleaned_data['itemvar'], None

                item = Item.objects.get(pk=itemid, event=self.request.event)
                if varid:
                    variation = ItemVariation.objects.get(pk=varid, item=item)
                else:
                    variation = None
                try:
                    ocm.add_position(item, variation,
                                     self.add_form.cleaned_data['price'],
                                     self.add_form.cleaned_data.get('addon_to'),
                                     self.add_form.cleaned_data.get('subevent'))
                except OrderError as e:
                    self.add_form.custom_error = str(e)
                    return False
        return True

    def _process_change(self, ocm):
        for p in self.positions:
            if not p.form.is_valid():
                return False

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
                elif p.form.cleaned_data['operation'] == 'subevent':
                    ocm.change_subevent(p, p.form.cleaned_data['subevent'])
                elif p.form.cleaned_data['operation'] == 'cancel':
                    ocm.cancel(p)
                elif p.form.cleaned_data['operation'] == 'split':
                    ocm.split(p)

            except OrderError as e:
                p.custom_error = str(e)
                return False
        return True

    def post(self, *args, **kwargs):
        notify = self.other_form.cleaned_data['notify'] if self.other_form.is_valid() else True
        ocm = OrderChangeManager(
            self.order,
            user=self.request.user,
            notify=notify
        )
        form_valid = self._process_add(ocm) and self._process_change(ocm) and self._process_other(ocm)

        if not form_valid:
            messages.error(self.request, _('An error occurred. Please see the details below.'))
        else:
            try:
                ocm.commit()
            except OrderError as e:
                messages.error(self.request, str(e))
            else:
                if notify:
                    messages.success(self.request, _('The order has been changed and the user has been notified.'))
                else:
                    messages.success(self.request, _('The order has been changed.'))
                return self._redirect_back()

        return self.get(*args, **kwargs)


class OrderModifyInformation(OrderQuestionsViewMixin, OrderView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/order/change_questions.html'

    def post(self, request, *args, **kwargs):
        failed = not self.save() or not self.invoice_form.is_valid()
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(request, *args, **kwargs)
        self.invoice_form.save()
        self.order.log_action('pretix.event.order.modified', user=request.user)
        if self.invoice_form.has_changed():
            success_message = ('The invoice address has been updated. If you want to generate a new invoice, '
                               'you need to do this manually.')
            messages.success(self.request, _(success_message))

        CachedTicket.objects.filter(order_position__order=self.order).delete()
        CachedCombinedTicket.objects.filter(order=self.order).delete()
        return redirect(self.get_order_url())


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
        changed = False
        if self.form.is_valid():
            new_email = self.form.cleaned_data['email']
            if new_email != old_email:
                changed = True
                self.order.log_action(
                    'pretix.event.order.contact.changed',
                    data={
                        'old_email': old_email,
                        'new_email': self.form.cleaned_data['email'],
                    },
                    user=self.request.user,
                )
            if self.form.cleaned_data['regenerate_secrets']:
                changed = True
                self.order.secret = generate_secret()
                for op in self.order.positions.all():
                    op.secret = generate_position_secret()
                    op.save()
                CachedTicket.objects.filter(order_position__order=self.order).delete()
                CachedCombinedTicket.objects.filter(order=self.order).delete()
                self.order.log_action('pretix.event.order.secret.changed', user=self.request.user)

            self.form.save()
            if changed:
                messages.success(self.request, _('The order has been changed.'))
            else:
                messages.success(self.request, _('Nothing about the order had to be changed.'))
            return redirect(self.get_order_url())
        return self.get(*args, **kwargs)


class OrderLocaleChange(OrderView):
    permission = 'can_change_orders'
    template_name = 'pretixcontrol/order/change_locale.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()
        ctx['form'] = self.form
        return ctx

    @cached_property
    def form(self):
        return OrderLocaleForm(
            instance=self.order,
            data=self.request.POST if self.request.method == "POST" else None
        )

    def post(self, *args, **kwargs):
        old_locale = self.order.locale
        if self.form.is_valid():
            self.order.log_action(
                'pretix.event.order.locale.changed',
                data={
                    'old_locale': old_locale,
                    'new_locale': self.form.cleaned_data['locale'],
                },
                user=self.request.user,
            )

            self.form.save()
            messages.success(self.request, _('The order has been changed.'))
            return redirect(self.get_order_url())
        return self.get(*args, **kwargs)


class OrderViewMixin:
    def get_object(self, queryset=None):
        try:
            return Order.objects.get(
                event=self.request.event,
                code=self.kwargs['code'].upper()
            )
        except Order.DoesNotExist:
            raise Http404()

    @cached_property
    def order(self):
        return self.get_object()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        return ctx


class OrderSendMail(EventPermissionRequiredMixin, OrderViewMixin, FormView):
    template_name = 'pretixcontrol/order/sendmail.html'
    permission = 'can_change_orders'
    form_class = OrderMailForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['order'] = Order.objects.get(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        )
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not send the email. See below for details.'))
        return super().form_invalid(form)

    def form_valid(self, form):
        tz = pytz.timezone(self.request.event.settings.timezone)
        order = Order.objects.get(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        )
        self.preview_output = {}
        try:
            invoice_name = order.invoice_address.name
            invoice_company = order.invoice_address.company
        except InvoiceAddress.DoesNotExist:
            invoice_name = ""
            invoice_company = ""
        with language(order.locale):
            email_context = {
                'event': order.event,
                'code': order.code,
                'date': date_format(order.datetime.astimezone(tz), 'SHORT_DATETIME_FORMAT'),
                'expire_date': date_format(order.expires, 'SHORT_DATE_FORMAT'),
                'url': build_absolute_uri(order.event, 'presale:event.order', kwargs={
                    'order': order.code,
                    'secret': order.secret
                }),
                'invoice_name': invoice_name,
                'invoice_company': invoice_company,
            }
        email_template = LazyI18nString(form.cleaned_data['message'])
        email_content = render_mail(email_template, email_context)[0]
        if self.request.POST.get('action') == 'preview':
            self.preview_output = []
            self.preview_output.append(
                _('Subject: {subject}').format(subject=form.cleaned_data['subject']))
            self.preview_output.append(email_content)
            return self.get(self.request, *self.args, **self.kwargs)
        else:
            try:
                order.send_mail(
                    form.cleaned_data['subject'], email_template,
                    email_context, 'pretix.event.order.email.custom_sent',
                    self.request.user
                )
                messages.success(self.request, _('Your message has been queued and will be sent to {}.'.format(order.email)))
            except SendMailException:
                messages.error(
                    self.request,
                    _('Failed to send mail to the following user: {}'.format(order.email))
                )
            return super(OrderSendMail, self).form_valid(form)

    def get_success_url(self):
        return reverse('control:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'code': self.kwargs['code']}
        )

    def get_context_data(self, *args, **kwargs):
        ctx = super().get_context_data(*args, **kwargs)
        ctx['preview_output'] = getattr(self, 'preview_output', None)
        return ctx


class OrderEmailHistory(EventPermissionRequiredMixin, OrderViewMixin, ListView):
    template_name = 'pretixcontrol/order/mail_history.html'
    permission = 'can_view_orders'
    model = LogEntry
    context_object_name = 'logs'
    paginate_by = 10

    def get_queryset(self):
        order = Order.objects.filter(
            event=self.request.event,
            code=self.kwargs['code'].upper()
        ).first()
        qs = order.all_logentries()
        qs = qs.filter(
            action_type__contains="order.email"
        )
        return qs


class AnswerDownload(EventPermissionRequiredMixin, OrderViewMixin, ListView):
    permission = 'can_view_orders'

    def get(self, request, *args, **kwargs):
        answid = kwargs.get('answer')
        token = request.GET.get('token', '')

        answer = get_object_or_404(QuestionAnswer, orderposition__order=self.order, id=answid)
        if not answer.file:
            raise Http404()
        if not check_token(request, answer, token):
            raise Http404(_("This link is no longer valid. Please go back, refresh the page, and try again."))

        ftype, ignored = mimetypes.guess_type(answer.file.name)
        resp = FileResponse(answer.file, content_type=ftype or 'application/binary')
        resp['Content-Disposition'] = 'attachment; filename="{}-{}-{}-{}"'.format(
            self.request.event.slug.upper(), self.order.code,
            answer.orderposition.positionid,
            os.path.basename(answer.file.name).split('.', 1)[1]
        )
        return resp


class OverView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/orders/overview.html'
    permission = 'can_view_orders'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data()

        subevent = None
        if self.request.GET.get("subevent", "") != "" and self.request.event.has_subevents:
            i = self.request.GET.get("subevent", "")
            try:
                subevent = self.request.event.subevents.get(pk=i)
            except SubEvent.DoesNotExist:
                pass

        ctx['items_by_category'], ctx['total'] = order_overview(self.request.event, subevent=subevent)
        ctx['subevent_warning'] = self.request.event.has_subevents and subevent and (
            OrderFee.objects.filter(order__event=self.request.event).exclude(value=0).exists()
        )
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


class ExportMixin:

    @cached_property
    def exporters(self):
        exporters = []
        responses = register_data_exporters.send(self.request.event)
        for receiver, response in responses:
            ex = response(self.request.event)
            if self.request.GET.get("identifier") and ex.identifier != self.request.GET.get("identifier"):
                continue

            # Use form parse cycle to generate useful defaults
            test_form = ExporterForm(data=self.request.GET, prefix=ex.identifier)
            test_form.fields = ex.export_form_fields
            test_form.is_valid()
            initial = {
                k: v for k, v in test_form.cleaned_data.items() if ex.identifier + "-" + k in self.request.GET
            }

            ex.form = ExporterForm(
                data=(self.request.POST if self.request.method == 'POST' else None),
                prefix=ex.identifier,
                initial=initial
            )
            ex.form.fields = ex.export_form_fields
            exporters.append(ex)
        return exporters


class ExportDoView(EventPermissionRequiredMixin, ExportMixin, AsyncAction, View):
    permission = 'can_view_orders'
    task = export

    def get_success_message(self, value):
        return None

    def get_success_url(self, value):
        return reverse('cachedfile.download', kwargs={'id': str(value)})

    def get_error_url(self):
        return reverse('control:event.orders.export', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug
        })

    @cached_property
    def exporter(self):
        for ex in self.exporters:
            if ex.identifier == self.request.POST.get("exporter"):
                return ex

    def post(self, request, *args, **kwargs):
        if not self.exporter:
            messages.error(self.request, _('The selected exporter was not found.'))
            return redirect('control:event.orders.export', kwargs={
                'event': self.request.event.slug,
                'organizer': self.request.event.organizer.slug
            })

        if not self.exporter.form.is_valid():
            messages.error(self.request, _('There was a problem processing your input. See below for error details.'))
            return self.get(request, *args, **kwargs)

        cf = CachedFile()
        cf.date = now()
        cf.expires = now() + timedelta(days=3)
        cf.save()
        return self.do(self.request.event.id, str(cf.id), self.exporter.identifier, self.exporter.form.cleaned_data)


class ExportView(EventPermissionRequiredMixin, ExportMixin, TemplateView):
    permission = 'can_view_orders'
    template_name = 'pretixcontrol/orders/export.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['exporters'] = self.exporters
        return ctx
