#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from pretix.base.models import CachedFile
from pretix.helpers.http import ChunkBasedFileResponse


class DownloadView(TemplateView):
    template_name = "pretixbase/cachedfiles/pending.html"

    @cached_property
    def object(self) -> CachedFile:
        try:
            o = get_object_or_404(CachedFile, id=self.kwargs['id'], web_download=True)
            if o.session_key:
                if o.session_key != self.request.session.session_key:
                    raise Http404()
            return o
        except (ValueError, ValidationError):   # Invalid URLs
            raise Http404()

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if 'ajax' in request.GET:
            return HttpResponse('1' if self.object.file else '0')
        elif self.object.file:
            resp = ChunkBasedFileResponse(self.object.file.file, content_type=self.object.type)
            resp['Content-Disposition'] = 'attachment; filename="{}"'.format(self.object.filename).encode('ascii', 'ignore')
            return resp
        else:
            return super().get(request, *args, **kwargs)
