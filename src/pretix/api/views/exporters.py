from datetime import timedelta

from celery.result import AsyncResult
from django.http import Http404, FileResponse
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.timezone import now
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.reverse import reverse

from pretix.api.serializers.exporters import ExporterSerializer, JobRunSerializer
from pretix.base.models import CachedFile
from pretix.base.services.export import export
from pretix.base.signals import register_data_exporters


class EventExportersViewSet(viewsets.ViewSet):
    permission = 'can_view_orders'

    @cached_property
    def exporters(self):
        exporters = []
        responses = register_data_exporters.send(self.request.event)
        for ex in sorted([response(self.request.event) for r, response in responses], key=lambda ex: str(ex.verbose_name)):
            ex.input_fields = ex.export_form_fields

            ex._serializer = JobRunSerializer(exporter=ex)
            exporters.append(ex)
        return exporters

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

    @action(detail=True, methods=['POST'])
    def run(self, *args, **kwargs):
        instance = self.get_object()
        serializer = JobRunSerializer(exporter=instance, data=self.request.data)
        serializer.is_valid(raise_exception=True)

        cf = CachedFile()
        cf.date = now()
        cf.expires = now() + timedelta(days=3)
        cf.save()
        async_result = export.apply_async(args=(self.request.event.id, str(cf.id), instance.identifier, serializer.data))

        return Response({
            'download': reverse('api-v1:exporters-download', kwargs={
                'organizer': self.request.event.organizer.slug,
                'event': self.request.event.slug,
                'pk': instance.identifier,
                'asyncid': str(async_result.id),
                'cfid': str(cf.id),
            }, request=self.request)
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['GET'], url_name='download', url_path='download/(?P<asyncid>[^/]+)/(?P<cfid>[^/]+)')
    def download(self, *args, **kwargs):
        cf = get_object_or_404(CachedFile, id=kwargs['cfid'])
        if cf.file:
            resp = FileResponse(cf.file.file, content_type=cf.type)
            resp['Content-Disposition'] = 'attachment; filename="{}"'.format(cf.filename)
            return resp

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
