#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
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
from django.db import transaction
from django.db.models import QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.functional import lazy
from django.utils.timezone import now
from django_scopes import scopes_disabled
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.reverse import reverse

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField

from ...api.serializers.fields import UploadedFileField
from ...base.models import CachedFile, OrderPosition, SalesChannel
from ...base.pdf import PdfLayoutValidator
from ...helpers.http import ChunkBasedFileResponse
from ...multidomain.utils import static_absolute
from .models import TicketLayout, TicketLayoutItem
from .tasks import bulk_render


class ItemAssignmentSerializer(I18nAwareModelSerializer):
    sales_channel = serializers.SlugRelatedField(
        slug_field='identifier',
        queryset=SalesChannel.objects.none(),
    )

    class Meta:
        model = TicketLayoutItem
        fields = ('id', 'layout', 'item', 'sales_channel')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sales_channel"].queryset = self.context["event"].organizer.sales_channels.all()


class NestedItemAssignmentSerializer(I18nAwareModelSerializer):
    sales_channel = serializers.SlugRelatedField(
        slug_field='identifier',
        queryset=SalesChannel.objects.none(),
    )

    class Meta:
        model = TicketLayoutItem
        fields = ('item', 'sales_channel')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sales_channel"].queryset = lazy(lambda: self.context["event"].organizer.sales_channels.all(), QuerySet)


class TicketLayoutSerializer(I18nAwareModelSerializer):
    layout = CompatibleJSONField(
        validators=[PdfLayoutValidator()]
    )
    item_assignments = NestedItemAssignmentSerializer(many=True, read_only=True)
    background = UploadedFileField(required=False, allow_null=True, allowed_types=(
        'application/pdf',
    ), max_size=settings.FILE_UPLOAD_MAX_SIZE_IMAGE)

    class Meta:
        model = TicketLayout
        fields = ('id', 'name', 'default', 'layout', 'background', 'item_assignments')

    def to_representation(self, instance):
        d = super().to_representation(instance)
        if not d['background']:
            d['background'] = static_absolute(instance.event, "pretixpresale/pdf/ticket_default_a4.pdf")
        return d

    def validate(self, attrs):
        if attrs.get('default') and self.context['event'].ticket_layouts.filter(default=True).exists:
            raise ValidationError('You cannot have two layouts with default = True')
        return attrs

    def create(self, validated_data):
        validated_data["event"] = self.context["event"]
        return super().create(validated_data)


class TicketLayoutViewSet(viewsets.ModelViewSet):
    serializer_class = TicketLayoutSerializer
    queryset = TicketLayout.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return self.request.event.ticket_layouts.all()

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            'event': self.request.event,
        }

    @transaction.atomic()
    def perform_destroy(self, instance):
        instance.log_action(
            action='pretix.plugins.ticketoutputpdf.layout.deleted',
            user=self.request.user, auth=self.request.auth
        )
        super().perform_destroy(instance)
        if not self.request.event.ticket_layouts.filter(default=True).exists():
            f = self.request.event.ticket_layouts.first()
            if f:
                f.default = True
                f.save(update_fields=['default'])

    @transaction.atomic()
    def perform_create(self, serializer):
        super().perform_create(serializer)
        serializer.instance.log_action(
            action='pretix.plugins.ticketoutputpdf.layout.added',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )

    @transaction.atomic()
    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            action='pretix.plugins.ticketoutputpdf.layout.changed',
            user=self.request.user,
            auth=self.request.auth,
            data=self.request.data,
        )


class TicketLayoutItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemAssignmentSerializer
    queryset = TicketLayoutItem.objects.none()
    lookup_field = 'id'

    def get_queryset(self):
        return TicketLayoutItem.objects.filter(item__event=self.request.event)

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            'event': self.request.event,
        }


with scopes_disabled():
    class RenderJobPartSerializer(serializers.Serializer):
        orderposition = serializers.PrimaryKeyRelatedField(
            queryset=OrderPosition.objects.none(),
            required=True,
            allow_null=False,
        )
        override_layout = serializers.PrimaryKeyRelatedField(
            queryset=TicketLayout.objects.none(),
            required=False,
            allow_null=True,
        )
        override_channel = serializers.SlugRelatedField(
            queryset=SalesChannel.objects.none(),
            slug_field='identifier',
            required=False,
            allow_null=True,
        )


class RenderJobSerializer(serializers.Serializer):
    parts = RenderJobPartSerializer(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parts'].child.fields['orderposition'].queryset = OrderPosition.objects.filter(order__event=self.context['event'])
        self.fields['parts'].child.fields['override_layout'].queryset = self.context['event'].ticket_layouts.all()
        self.fields['parts'].child.fields['override_channel'].queryset = self.context['event'].organizer.sales_channels.all()

    def validate(self, attrs):
        if len(attrs["parts"]) > 1000:
            raise ValidationError({"parts": ["Please do not submit more than 1000 parts."]})
        return super().validate(attrs)


class TicketRendererViewSet(viewsets.ViewSet):
    permission = 'can_view_orders'

    def get_serializer_kwargs(self):
        return {}

    def list(self, request, *args, **kwargs):
        raise Http404()

    def retrieve(self, request, *args, **kwargs):
        raise Http404()

    def update(self, request, *args, **kwargs):
        raise Http404()

    def partial_update(self, request, *args, **kwargs):
        raise Http404()

    def destroy(self, request, *args, **kwargs):
        raise Http404()

    @action(detail=False, methods=['GET'], url_name='download', url_path='download/(?P<asyncid>[^/]+)/(?P<cfid>[^/]+)')
    def download(self, *args, **kwargs):
        cf = get_object_or_404(CachedFile, id=kwargs['cfid'])
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
            },
            status=status.HTTP_409_CONFLICT
        )

    @action(detail=False, methods=['POST'])
    def render_batch(self, *args, **kwargs):
        serializer = RenderJobSerializer(data=self.request.data, context={
            "event": self.request.event,
        })
        serializer.is_valid(raise_exception=True)

        cf = CachedFile(web_download=False)
        cf.date = now()
        cf.expires = now() + timedelta(hours=24)
        cf.save()
        async_result = bulk_render.apply_async(args=(
            self.request.event.id,
            str(cf.id),
            [
                {
                    "orderposition": r["orderposition"].id,
                    "override_layout": r["override_layout"].id if r.get("override_layout") else None,
                    "override_channel": r["override_channel"].id if r.get("override_channel") else None,
                } for r in serializer.validated_data["parts"]
            ]
        ))

        url_kwargs = {
            'asyncid': str(async_result.id),
            'cfid': str(cf.id),
        }
        url_kwargs.update(self.kwargs)
        return Response({
            'download': reverse('api-v1:ticketpdfrenderer-download', kwargs=url_kwargs, request=self.request)
        }, status=status.HTTP_202_ACCEPTED)
