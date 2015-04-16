from io import StringIO, BytesIO
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property
from django.views.generic import TemplateView, View
from django.http import HttpResponseNotFound, HttpResponseForbidden, HttpResponse
from pretix.base.models import Order, OrderPosition
from pretix.base.signals import register_payment_providers
from pretix.presale.views import EventViewMixin, EventLoginRequiredMixin, CartDisplayMixin
from pretix.presale.views.checkout import QuestionsViewMixin
from django.contrib.staticfiles import finders


class OrderDetailMixin:

    @cached_property
    def order(self):
        try:
            return Order.objects.current.get(
                user=self.request.user,
                event=self.request.event,
                code=self.kwargs['order'],
            )
        except Order.DoesNotExist:
            return None


class OrderDetails(EventViewMixin, EventLoginRequiredMixin, OrderDetailMixin,
                   CartDisplayMixin, TemplateView):
    template_name = "pretixpresale/event/order.html"

    def get(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        return super().get(request, *args, **kwargs)

    @cached_property
    def payment_provider(self):
        responses = register_payment_providers.send(self.request.event)
        for receiver, response in responses:
            provider = response(self.request.event)
            if provider.identifier == self.order.payment_provider:
                return provider

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['can_download'] = (
            self.request.event.settings.ticket_download
            and now() > self.request.event.settings.ticket_download_date
            and self.order.status == Order.STATUS_PAID
        )
        ctx['cart'] = self.get_cart(
            answers=True,
            queryset=OrderPosition.objects.current.filter(order=self.order)
        )
        if self.order.status == Order.STATUS_PENDING:
            ctx['payment'] = self.payment_provider.order_pending_render(self.request, self.order)
        elif self.order.status == Order.STATUS_PAID:
            ctx['payment'] = self.payment_provider.order_paid_render(self.request, self.order)
        return ctx


class OrderModify(EventViewMixin, EventLoginRequiredMixin, OrderDetailMixin,
                  QuestionsViewMixin, TemplateView):
    template_name = "pretixpresale/event/order_modify.html"

    @cached_property
    def positions(self):
        return list(self.order.positions.order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            'variation__values', 'variation__values__prop',
            'item__questions', 'answers'
        ))

    def post(self, request, *args, **kwargs):
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        if not self.order.can_modify_answers:
            return HttpResponseForbidden(_('You cannot modify this order'))
        failed = not self.save()
        if failed:
            messages.error(self.request,
                           _("We had difficulties processing your input. Please review the errors below."))
            return self.get(*args, **kwargs)
        return redirect(reverse('presale:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': self.order.code,
        }))

    def get(self, request, *args, **kwargs):
        self.request = request
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        if not self.order.can_modify_answers:
            return HttpResponseForbidden(_('You cannot modify this order'))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        ctx['forms'] = self.forms
        return ctx


class OrderCancel(EventViewMixin, EventLoginRequiredMixin, OrderDetailMixin,
                  TemplateView):
    template_name = "pretixpresale/event/order_cancel.html"

    def post(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            return HttpResponseForbidden(_('You cannot cancel this order'))
        order = self.order.clone()
        order.status = Order.STATUS_CANCELLED
        order.save()
        return redirect(reverse('presale:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': order.code,
        }))

    def get(self, request, *args, **kwargs):
        self.kwargs = kwargs
        if not self.order:
            return HttpResponseNotFound(_('Unknown order code or order does belong to another user.'))
        if self.order.status not in (Order.STATUS_PENDING, Order.STATUS_EXPIRED):
            return HttpResponseForbidden(_('You cannot cancel this order'))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['order'] = self.order
        return ctx


class OrderDownload(EventViewMixin, EventLoginRequiredMixin, OrderDetailMixin,
                    View):

    def get_order_url(self):
        return reverse('presale:event.order', kwargs={
            'event': self.request.event.slug,
            'organizer': self.request.event.organizer.slug,
            'order': self.order.code,
        })

    def get(self, request, *args, **kwargs):
        from reportlab.graphics.shapes import Drawing
        from reportlab.pdfgen import canvas
        from reportlab.lib import pagesizes, units
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics import renderPDF
        from PyPDF2 import PdfFileWriter, PdfFileReader

        if self.order.status != Order.STATUS_PAID:
            messages.error(request, _('Order is not paid.'))
            return redirect(self.get_order_url())
        if not self.request.event.settings.ticket_download or now() < self.request.event.settings.ticket_download_date:
            messages.error(request, _('Ticket download is not (yet) enabled.'))
            return redirect(self.get_order_url())

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="order%s%s.pdf"' % (request.event.slug, self.order.code)

        pagesize = request.event.settings.get('ticketpdf_pagesize', default='A4')
        if hasattr(pagesizes, pagesize):
            pagesize = getattr(pagesizes, pagesize)
        else:
            pagesize = pagesizes.A4
        defaultfname = finders.find('pretixpresale/pdf/ticket_default_a4.pdf')
        fname = request.event.settings.get('ticketpdf_background', default=defaultfname)
        # TODO: Handle file objects

        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=pagesize)

        for op in self.order.positions.all().select_related('item', 'variation'):
            p.setFont("Helvetica", 22)
            p.drawString(15 * units.mm, 235 * units.mm, request.event.name)

            p.setFont("Helvetica", 17)
            item = op.item.name
            if op.variation:
                item += " – " + str(op.variation)
            p.drawString(15 * units.mm, 220 * units.mm, item)

            p.setFont("Helvetica", 17)
            p.drawString(15 * units.mm, 210 * units.mm, "%s %s" % (str(op.price), request.event.currency))

            reqs = 80 * units.mm
            qrw = QrCodeWidget(op.identity, barLevel='H')
            b = qrw.getBounds()
            w = b[2] - b[0]
            h = b[3] - b[1]
            d = Drawing(reqs, reqs, transform=[reqs / w, 0, 0, reqs / h, 0, 0])
            d.add(qrw)
            renderPDF.draw(d, p, 10 * units.mm, 130 * units.mm)

            p.setFont("Helvetica", 11)
            p.drawString(15 * units.mm, 130 * units.mm, op.identity)

            p.showPage()

        p.save()

        buffer.seek(0)
        new_pdf = PdfFileReader(buffer)
        output = PdfFileWriter()
        for page in new_pdf.pages:
            bg_pdf = PdfFileReader(open(fname, "rb"))
            bg_page = bg_pdf.getPage(0)
            bg_page.mergePage(page)
            output.addPage(bg_page)

        output.write(response)
        return response
