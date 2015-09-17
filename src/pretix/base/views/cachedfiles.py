from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from pretix.base.models import CachedFile


class DownloadView(TemplateView):
    template_name = "pretixbase/cachedfiles/pending.html"

    @cached_property
    def object(self):
        return get_object_or_404(CachedFile, id=self.kwargs['id'])

    def get(self, request, *args, **kwargs):
        if 'ajax' in request.GET:
            return HttpResponse('1' if self.object.file else '0')
        elif self.object.file:
            return redirect(self.object.file.url)
        else:
            return super().get(request, *args, **kwargs)
