import os

from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from pretix.base.models import CachedFile


class DownloadView(TemplateView):
    template_name = "pretixbase/cachedfiles/pending.html"

    @cached_property
    def object(self) -> CachedFile:
        try:
            return get_object_or_404(CachedFile, id=self.kwargs['id'])
        except ValueError:   # Invalid URLs
            raise Http404()

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if 'ajax' in request.GET:
            return HttpResponse('1' if self.object.file else '0')
        elif self.object.file:
            resp = FileResponse(self.object.file.file, content_type=self.object.type)
            _, ext = os.path.splitext(self.object.filename)
            resp['Content-Disposition'] = 'attachment; filename="{}{}"'.format(self.object.id, ext)
            return resp
        else:
            return super().get(request, *args, **kwargs)
