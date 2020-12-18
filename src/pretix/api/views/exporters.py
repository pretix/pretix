from datetime import timedelta

from celery.result import AsyncResult
from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.timezone import now
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.reverse import reverse

from pretix.api.serializers.exporters import (
    ExporterSerializer, JobRunSerializer,
)
from pretix.base.models import CachedFile, Device, TeamAPIToken
from pretix.base.services.export import export, multiexport
from pretix.base.signals import (
    register_data_exporters, register_multievent_data_exporters,
)
from pretix.helpers.http import ChunkBasedFileResponse


class ExportersMixin:
    def list(self, request, *args, **kwargs):
        res = ExporterSerializer(self.exporters, many=True)
        return Response({
            "count": len(self.exporters),
            "next": None,
            "previous": None,
            "results": res.data
        })

    def get_object(self):
        instances = [e for e in self.exporters if e.identifier == self.kwargs.get('pk')]
        if not instances:
            raise Http404()
        return instances[0]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ExporterSerializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['GET'], url_name='download', url_path='download/(?P<asyncid>[^/]+)/(?P<cfid>[^/]+)')
    def download(self, *args, **kwargs):
        cf = get_object_or_404(CachedFile, id=kwargs['cfid'])
        if cf.file:
            resp = ChunkBasedFileResponse(cf.file.file, content_type=cf.type)
            resp['Content-Disposition'] = 'attachment; filename="{}"'.format(cf.filename)
            return resp
        elif not settings.HAS_CELERY:
            return Response(
                {'status': 'failed', 'message': 'Unknown file ID or export failed'},
                status=status.HTTP_410_GONE
            )

        res = AsyncResult(kwargs['asyncid'])
        if res.failed():
            if isinstance(res.info, dict) and res.info['exc_type'] == 'ExportError':
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
                'percentage': res.result.get('value', None) if res.result else None,
            },
            status=status.HTTP_409_CONFLICT
        )

    @action(detail=True, methods=['POST'])
    def run(self, *args, **kwargs):
        instance = self.get_object()
        serializer = JobRunSerializer(exporter=instance, data=self.request.data, **self.get_serializer_kwargs())
        serializer.is_valid(raise_exception=True)

        cf = CachedFile(web_download=False)
        cf.date = now()
        cf.expires = now() + timedelta(days=3)
        cf.save()
        d = serializer.data
        for k, v in d.items():
            if isinstance(v, set):
                d[k] = list(v)
        async_result = self.do_export(cf, instance, d)

        url_kwargs = {
            'asyncid': str(async_result.id),
            'cfid': str(cf.id),
        }
        url_kwargs.update(self.kwargs)
        return Response({
            'download': reverse('api-v1:exporters-download', kwargs=url_kwargs, request=self.request)
        }, status=status.HTTP_202_ACCEPTED)


class EventExportersViewSet(ExportersMixin, viewsets.ViewSet):
    permission = 'can_view_orders'

    def get_serializer_kwargs(self):
        return {}

    @cached_property
    def exporters(self):
        exporters = []
        responses = register_data_exporters.send(self.request.event)
        for ex in sorted([response(self.request.event) for r, response in responses], key=lambda ex: str(ex.verbose_name)):
            ex._serializer = JobRunSerializer(exporter=ex)
            exporters.append(ex)
        return exporters

    def do_export(self, cf, instance, data):
        return export.apply_async(args=(self.request.event.id, str(cf.id), instance.identifier, data))


class OrganizerExportersViewSet(ExportersMixin, viewsets.ViewSet):
    permission = None

    @cached_property
    def exporters(self):
        exporters = []
        events = (self.request.auth or self.request.user).get_events_with_permission('can_view_orders', request=self.request).filter(
            organizer=self.request.organizer
        )
        responses = register_multievent_data_exporters.send(self.request.organizer)
        for ex in sorted([response(events) for r, response in responses if response], key=lambda ex: str(ex.verbose_name)):
            ex._serializer = JobRunSerializer(exporter=ex, events=events)
            exporters.append(ex)
        return exporters

    def get_serializer_kwargs(self):
        return {
            'events': self.request.auth.get_events_with_permission('can_view_orders', request=self.request).filter(
                organizer=self.request.organizer
            )
        }

    def do_export(self, cf, instance, data):
        return multiexport.apply_async(kwargs={
            'organizer': self.request.organizer.id,
            'user': self.request.user.id if self.request.user.is_authenticated else None,
            'token': self.request.auth.pk if isinstance(self.request.auth, TeamAPIToken) else None,
            'device': self.request.auth.pk if isinstance(self.request.auth, Device) else None,
            'fileid': str(cf.id),
            'provider': instance.identifier,
            'form_data': data
        })
