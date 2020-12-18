import json
import logging
import mimetypes
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import (
    FileResponse, HttpResponse, HttpResponseBadRequest, JsonResponse,
)
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.views.generic import TemplateView
from PyPDF2 import PdfFileWriter
from reportlab.lib.units import mm

from pretix.base.i18n import language
from pretix.base.models import CachedFile, InvoiceAddress, OrderPosition
from pretix.base.pdf import get_variables
from pretix.base.settings import PERSON_NAME_SCHEMES
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.helpers.database import rolledback_transaction
from pretix.presale.style import get_fonts

logger = logging.getLogger(__name__)


class BaseEditorView(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/pdf/index.html'
    permission = 'can_change_settings'
    accepted_formats = (
        'application/pdf',
    )
    maxfilesize = 1024 * 1024 * 10
    minfilesize = 10
    title = None

    def get(self, request, *args, **kwargs):
        resp = super().get(request, *args, **kwargs)
        resp._csp_ignore = True
        return resp

    def process_upload(self):
        f = self.request.FILES.get('background')
        error = False
        if f.size > self.maxfilesize:
            error = _('The uploaded PDF file is too large.')
        if f.size < self.minfilesize:
            error = _('The uploaded PDF file is too small.')
        if mimetypes.guess_type(f.name)[0] not in self.accepted_formats:
            error = _('Please only upload PDF files.')
        # if there was an error, add error message to response_data and return
        if error:
            return error, None
        return None, f

    def _get_preview_position(self):
        item = self.request.event.items.create(name=_("Sample product"), default_price=42.23,
                                               description=_("Sample product description"))
        item2 = self.request.event.items.create(name=_("Sample workshop"), default_price=23.40)

        from pretix.base.models import Order
        order = self.request.event.orders.create(status=Order.STATUS_PENDING, datetime=now(),
                                                 email='sample@pretix.eu',
                                                 locale=self.request.event.settings.locale,
                                                 expires=now(), code="PREVIEW1234", total=119)

        scheme = PERSON_NAME_SCHEMES[self.request.event.settings.name_scheme]
        sample = {k: str(v) for k, v in scheme['sample'].items()}
        p = order.positions.create(item=item, attendee_name_parts=sample, price=item.default_price)
        order.positions.create(item=item2, attendee_name_parts=sample, price=item.default_price, addon_to=p)
        order.positions.create(item=item2, attendee_name_parts=sample, price=item.default_price, addon_to=p)

        InvoiceAddress.objects.create(order=order, name_parts=sample, company=_("Sample company"))
        return p

    def generate(self, p: OrderPosition, override_layout=None, override_background=None):
        raise NotImplementedError()

    def get_layout_settings_key(self):
        raise NotImplementedError()

    def get_background_settings_key(self):
        raise NotImplementedError()

    def get_default_background(self):
        raise NotImplementedError()

    def get_current_background(self):
        return (
            self.request.event.settings.get(self.get_background_settings_key()).url
            if self.request.event.settings.get(self.get_background_settings_key())
            else self.get_default_background()
        )

    def get_current_layout(self):
        return self.request.event.settings.get(self.get_layout_settings_key(), as_type=list)

    def save_layout(self):
        self.request.event.settings.set(self.get_layout_settings_key(), self.request.POST.get("data"))

    def save_background(self, f: CachedFile):
        fexisting = self.request.event.settings.get(self.get_background_settings_key(), as_type=File)
        if fexisting:
            try:
                default_storage.delete(fexisting.name)
            except OSError:  # pragma: no cover
                logger.error('Deleting file %s failed.' % fexisting.name)

        # Create new file
        nonce = get_random_string(length=8)
        fname = 'pub/%s-%s/%s/%s.%s.%s' % (
            'event', 'settings', self.request.event.pk, self.get_layout_settings_key(), nonce, 'pdf'
        )
        newname = default_storage.save(fname, f.file)
        self.request.event.settings.set(self.get_background_settings_key(), 'file://' + newname)

    def post(self, request, *args, **kwargs):
        if "emptybackground" in request.POST:
            p = PdfFileWriter()
            try:
                p.addBlankPage(
                    width=float(request.POST.get('width')) * mm,
                    height=float(request.POST.get('height')) * mm,
                )
            except ValueError:
                return JsonResponse({
                    "status": "error",
                    "error": "Invalid height/width given."
                })
            buffer = BytesIO()
            p.write(buffer)
            buffer.seek(0)
            c = CachedFile(web_download=True)
            c.expires = now() + timedelta(days=7)
            c.date = now()
            c.filename = 'background_preview.pdf'
            c.type = 'application/pdf'
            c.save()
            c.file.save('empty.pdf', ContentFile(buffer.read()))
            c.refresh_from_db()
            return JsonResponse({
                "status": "ok",
                "id": c.id,
                "url": reverse('control:pdf.background', kwargs={
                    'event': request.event.slug,
                    'organizer': request.organizer.slug,
                    'filename': str(c.id)
                })
            })

        if "background" in request.FILES:
            error, fileobj = self.process_upload()
            if error:
                return JsonResponse({
                    "status": "error",
                    "error": error
                })
            c = CachedFile(web_download=True)
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
                "url": reverse('control:pdf.background', kwargs={
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
            with rolledback_transaction(), language(request.event.settings.locale, request.event.settings.region):
                p = self._get_preview_position()
                fname, mimet, data = self.generate(
                    p,
                    override_layout=(json.loads(self.request.POST.get("data"))
                                     if self.request.POST.get("data") else None),
                    override_background=cf.file if cf else None
                )

            resp = HttpResponse(data, content_type=mimet)
            ftype = fname.split(".")[-1]
            resp['Content-Disposition'] = 'attachment; filename="ticket-preview.{}"'.format(ftype)
            return resp
        elif "data" in request.POST:
            if cf:
                self.save_background(cf)
            self.save_layout()
            return JsonResponse({'status': 'ok'})
        return HttpResponseBadRequest()

    def get_variables(self):
        return get_variables(self.request.event)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['fonts'] = get_fonts()
        ctx['pdf'] = self.get_current_background()
        ctx['variables'] = self.get_variables()
        ctx['layout'] = json.dumps(self.get_current_layout())
        ctx['title'] = self.title
        ctx['locales'] = [p for p in settings.LANGUAGES if p[0] in self.request.event.settings.locales]
        return ctx


class FontsCSSView(TemplateView):
    content_type = 'text/css'
    template_name = 'pretixcontrol/pdf/webfonts.css'

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
