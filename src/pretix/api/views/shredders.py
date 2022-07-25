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
from datetime import timedelta

from celery.result import AsyncResult
from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.timezone import now
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.reverse import reverse

from pretix.api.serializers.shredders import (
    JobRunSerializer, ShredderSerializer,
)
from pretix.base.models import CachedFile
from pretix.base.services.shredder import export, shred
from pretix.base.shredder import shred_constraints
from pretix.helpers.http import ChunkBasedFileResponse


class ShreddersMixin:
    def list(self, request, *args, **kwargs):
        res = ShredderSerializer(self.shredders, many=True)
        return Response({
            "count": len(self.shredders),
            "next": None,
            "previous": None,
            "results": res.data
        })

    def get_object(self):
        instances = [e for e in self.shredders if e.identifier == self.kwargs.get('pk')]
        if not instances:
            raise Http404()
        return instances[0]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ShredderSerializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['GET'], url_name='download', url_path='download/(?P<asyncid>[^/]+)/(?P<cfid>[^/]+)')
    def download(self, *args, **kwargs):
        cf = get_object_or_404(
            CachedFile,
            id=kwargs['cfid'],
            session_key=f'api-shredder-{str(type(self.request.user or self.request.auth))}-{(self.request.user or self.request.auth).pk}'
        )
        if cf.file:
            resp = ChunkBasedFileResponse(cf.file.file, content_type=cf.type)
            resp['Content-Disposition'] = 'attachment; filename="{}"'.format(cf.filename).encode("ascii", "ignore")
            return resp
        elif not settings.HAS_CELERY:
            return Response(
                {'status': 'failed', 'message': 'Unknown file ID or export failed'},
                status=status.HTTP_410_GONE
            )

        res = AsyncResult(kwargs['asyncid'])
        if res.failed():
            if isinstance(res.info, dict) and res.info['exc_type'] in ('ShredError', 'ExportError'):
                msg = res.info['exc_message']
            else:
                msg = 'Internal error'
            return Response(
                {'status': 'failed', 'message': msg},
                status=status.HTTP_410_GONE
            )

        return Response(
            {
                'status': 'running' if res.state in ('PROGRESS', 'STARTED', 'SUCCESS') else 'waiting',
            },
            status=status.HTTP_409_CONFLICT
        )

    @action(detail=False, methods=['GET'], url_name='status', url_path='status/(?P<asyncid>[^/]+)/(?P<cfid>[^/]+)')
    def status(self, *args, **kwargs):
        if settings.HAS_CELERY:
            res = AsyncResult(kwargs['asyncid'])
            if res.failed():
                if isinstance(res.info, dict) and res.info['exc_type'] in ('ShredError', 'ExportError'):
                    msg = res.info['exc_message']
                else:
                    msg = 'Internal error'
                return Response(
                    {'status': 'failed', 'message': msg},
                    status=status.HTTP_417_EXPECTATION_FAILED
                )
            elif res.successful():
                return Response(
                    {'status': 'ok', 'message': 'OK'},
                    status=status.HTTP_200_OK
                )

        try:
            CachedFile.objects.get(
                id=kwargs['cfid'],
                session_key=f'api-shredder-{str(type(self.request.user or self.request.auth))}-{(self.request.user or self.request.auth).pk}'
            )
        except CachedFile.DoesNotExist:
            return Response(
                {'status': 'gone', 'message': 'May have succeeded or timed out'},
                status=status.HTTP_410_GONE
            )

        return Response(
            {
                'status': 'running' if res.state in ('PROGRESS', 'STARTED', 'SUCCESS') else 'waiting',
            },
            status=status.HTTP_409_CONFLICT
        )

    @action(detail=False, methods=['POST'], url_name='shred', url_path='shred/(?P<asyncid>[^/]+)/(?P<cfid>[^/]+)')
    def shred(self, *args, **kwargs):
        cf = get_object_or_404(
            CachedFile,
            id=kwargs['cfid'],
            session_key=f'api-shredder-{str(type(self.request.user or self.request.auth))}-{(self.request.user or self.request.auth).pk}'
        )
        if cf.file:
            async_result = self.do_shred(cf)
            url_kwargs = {
                'asyncid': str(async_result.id),
                'cfid': str(cf.id),
            }
            url_kwargs.update(self.kwargs)
            return Response({
                'status': reverse('api-v1:shredders-status', kwargs=url_kwargs, request=self.request),
            }, status=status.HTTP_202_ACCEPTED)
        elif not settings.HAS_CELERY:
            return Response(
                {'status': 'failed', 'message': 'Unknown file ID or export failed'},
                status=status.HTTP_410_GONE
            )

        res = AsyncResult(kwargs['asyncid'])
        if res.failed():
            if isinstance(res.info, dict) and res.info['exc_type'] in ('ShredError', 'ExportError'):
                msg = res.info['exc_message']
            else:
                msg = 'Internal error'
            return Response(
                {'status': 'failed', 'message': msg},
                status=status.HTTP_410_GONE
            )

        return Response(
            {
                'status': 'running' if res.state in ('PROGRESS', 'STARTED', 'SUCCESS') else 'waiting',
            },
            status=status.HTTP_409_CONFLICT
        )

    @action(detail=False, methods=['POST'])
    def export(self, *args, **kwargs):
        serializer = JobRunSerializer(shredders=self.shredders, data=self.request.data, **self.get_serializer_kwargs())
        serializer.is_valid(raise_exception=True)

        cf = CachedFile(web_download=False)
        cf.date = now()
        cf.expires = now() + timedelta(hours=2)
        cf.session_key = f'api-shredder-{str(type(self.request.user or self.request.auth))}-{(self.request.user or self.request.auth).pk}'
        cf.save()
        d = serializer.data
        for k, v in d.items():
            if isinstance(v, set):
                d[k] = list(v)
        async_result = self.do_export(cf, serializer.validated_data['shredders'])

        url_kwargs = {
            'asyncid': str(async_result.id),
            'cfid': str(cf.id),
        }
        url_kwargs.update(self.kwargs)
        return Response({
            'download': reverse('api-v1:shredders-download', kwargs=url_kwargs, request=self.request),
            'shred': reverse('api-v1:shredders-shred', kwargs=url_kwargs, request=self.request),
        }, status=status.HTTP_202_ACCEPTED)


class EventShreddersViewSet(ShreddersMixin, viewsets.ViewSet):
    permission = 'can_change_orders'

    def get_serializer_kwargs(self):
        return {}

    @cached_property
    def shredders(self):
        shredders = []
        for k, v in sorted(self.request.event.get_data_shredders().items(), key=lambda s: s[1].verbose_name):
            shredders.append(v)
        return shredders

    def do_export(self, cf, shredders):
        constr = shred_constraints(self.request.event)
        if constr:
            raise ValidationError(constr)

        return export.apply_async(args=(
            self.request.event.id,
            list(shredders),
            f'api-shredder-{str(type(self.request.user or self.request.auth))}-{(self.request.user or self.request.auth).pk}',
            str(cf.pk)
        ))

    def do_shred(self, cf):
        constr = shred_constraints(self.request.event)
        if constr:
            raise ValidationError(constr)

        return shred.apply_async(args=(
            self.request.event.id,
            str(cf.pk),
            True,
        ))
