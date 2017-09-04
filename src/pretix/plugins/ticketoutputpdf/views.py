import json
import logging
import mimetypes
from datetime import timedelta

from django.core.files import File
from django.core.files.storage import default_storage
from django.http import (
    FileResponse, HttpResponse, HttpResponseBadRequest, JsonResponse,
)
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import ugettext as _
from django.views.generic import TemplateView

from pretix.base.i18n import language
from pretix.base.models import (
    CachedCombinedTicket, CachedFile, CachedTicket, InvoiceAddress,
)
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import ChartContainingView
from pretix.helpers.database import rolledback_transaction
from pretix.plugins.ticketoutputpdf.signals import get_fonts

from .ticketoutput import PdfTicketOutput

logger = logging.getLogger(__name__)


class EditorView(EventPermissionRequiredMixin, ChartContainingView, TemplateView):
    template_name = 'pretixplugins/ticketoutputpdf/index.html'
    permission = 'can_change_settings'
    accepted_formats = (
        'application/pdf',
    )
    maxfilesize = 1024 * 1024 * 10
    minfilesize = 10

    def process_upload(self):
        f = self.request.FILES.get('background')
        error = False
        if f.size > self.maxfilesize:
            error = _('The uploaded PDF file is to large.')
        if f.size < self.minfilesize:
            error = _('The uploaded PDF file is to small.')
        if mimetypes.guess_type(f.name)[0] not in self.accepted_formats:
            error = _('Please only upload PDF files.')
        # if there was an error, add error message to response_data and return
        if error:
            return error, None
        return None, f

    def post(self, request, *args, **kwargs):
        if "background" in request.FILES:
            error, fileobj = self.process_upload()
            if error:
                return JsonResponse({
                    "status": "error",
                    "error": error
                })
            c = CachedFile()
            c.expires = now() + timedelta(days=7)
            c.date = now()
            c.filename = 'background_preview.pdf'
            c.type = 'application/pdf'
            c.file = fileobj
            c.save()
            c.refresh_from_db()
            return JsonResponse({
                "status": "ok",
                "id": c.id,
                "url": reverse('plugins:ticketoutputpdf:pdf', kwargs={
                    'event': request.event.slug,
                    'organizer': request.organizer.slug,
                    'filename': str(c.id)
                })
            })

        cf = None
        if request.POST.get("background", "").strip():
            try:
                cf = CachedFile.objects.get(id=request.POST.get("background"))
            except CachedFile.DoesNotExist:
                pass

        if "preview" in request.POST:
            with rolledback_transaction(), language(request.event.settings.locale):
                item = request.event.items.create(name=_("Sample product"), default_price=42.23,
                                                  description=_("Sample product description"))
                item2 = request.event.items.create(name=_("Sample workshop"), default_price=23.40)

                from pretix.base.models import Order
                order = request.event.orders.create(status=Order.STATUS_PENDING, datetime=now(),
                                                    email='sample@pretix.eu',
                                                    expires=now(), code="PREVIEW1234", total=119)

                p = order.positions.create(item=item, attendee_name=_("John Doe"), price=item.default_price)
                order.positions.create(item=item2, attendee_name=_("John Doe"), price=item.default_price, addon_to=p)
                order.positions.create(item=item2, attendee_name=_("John Doe"), price=item.default_price, addon_to=p)

                InvoiceAddress.objects.create(order=order, name=_("John Doe"), company=_("Sample company"))

                prov = PdfTicketOutput(request.event,
                                       override_layout=(json.loads(request.POST.get("data"))
                                                        if request.POST.get("data") else None),
                                       override_background=cf.file if cf else None)
                fname, mimet, data = prov.generate(p)

            resp = HttpResponse(data, content_type=mimet)
            ftype = fname.split(".")[-1]
            resp['Content-Disposition'] = 'attachment; filename="ticket-preview.{}"'.format(ftype)
            return resp
        elif "data" in request.POST:
            if cf:
                fexisting = request.event.settings.get('ticketoutput_pdf_layout', as_type=File)
                if fexisting:
                    try:
                        default_storage.delete(fexisting.name)
                    except OSError:  # pragma: no cover
                        logger.error('Deleting file %s failed.' % fexisting.name)

                # Create new file
                nonce = get_random_string(length=8)
                fname = '%s-%s/%s/%s.%s.%s' % (
                    'event', 'settings', self.request.event.pk, 'ticketoutput_pdf_layout', nonce, 'pdf'
                )
                newname = default_storage.save(fname, cf.file)
                request.event.settings.set('ticketoutput_pdf_background', 'file://' + newname)

            request.event.settings.set('ticketoutput_pdf_layout', request.POST.get("data"))

            CachedTicket.objects.filter(
                order_position__order__event=self.request.event, provider='pdf'
            ).delete()
            CachedCombinedTicket.objects.filter(
                order__event=self.request.event, provider='pdf'
            ).delete()

            return JsonResponse({'status': 'ok'})
        return HttpResponseBadRequest()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        prov = PdfTicketOutput(self.request.event)
        ctx['fonts'] = get_fonts()
        ctx['layout'] = json.dumps(
            self.request.event.settings.get('ticketoutput_pdf_layout', as_type=list)
            or prov._default_layout()
        )
        return ctx


class FontsCSSView(TemplateView):
    content_type = 'text/css'
    template_name = 'pretixplugins/ticketoutputpdf/webfonts.css'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['fonts'] = get_fonts()
        return ctx


class PdfView(TemplateView):
    def get(self, request, *args, **kwargs):
        cf = get_object_or_404(CachedFile, id=kwargs.get("filename"), filename="background_preview.pdf")
        resp = FileResponse(cf.file, content_type='application/pdf')
        resp['Content-Disposition'] = 'attachment; filename="{}"'.format(cf.filename)
        return resp
