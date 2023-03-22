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

import django_filters
from django.db.models import Q
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response

from pretix.base.models import Device
from pretix.base.models.organizer import TeamAPIToken

from .models import BankImportJob, BankTransaction
from .tasks import process_banktransfers


class BankTransactionSerializer(serializers.ModelSerializer):
    order = serializers.SlugRelatedField(slug_field='code', read_only=True)
    message = serializers.CharField(read_only=True)
    state = serializers.CharField(read_only=True)
    checksum = serializers.CharField(read_only=True)

    class Meta:
        model = BankTransaction
        fields = ('state', 'message', 'checksum', 'payer', 'reference', 'amount', 'date', 'order',
                  'comment', 'iban', 'bic', 'currency')


class BankImportJobSerializer(serializers.ModelSerializer):
    event = serializers.SlugRelatedField(slug_field='slug', read_only=True, allow_null=True)
    transactions = BankTransactionSerializer(many=True, read_only=False)
    state = serializers.CharField(read_only=True)
    partial = False

    class Meta:
        model = BankImportJob
        fields = ('id', 'event', 'created', 'state', 'transactions', 'currency')

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        self.fields['event'].read_only = False
        self.fields['event'].queryset = self.organizer.events.all()
        super().__init__(*args, **kwargs)

    def validate(self, attrs):
        if not attrs.get("event"):
            if "currency" not in attrs:
                currencies = list(
                    self.organizer.events.order_by('currency').values_list('currency', flat=True).distinct()
                )
                if len(currencies) != 1:
                    raise ValidationError({"currency": ["Currency is ambiguous, please set explicitly."]})
                else:
                    attrs["currency"] = currencies[0]
        return attrs

    def create(self, validated_data):
        trans_data = validated_data.pop('transactions')
        job = BankImportJob.objects.create(organizer=self.organizer, **validated_data)
        job._data = trans_data
        return job


class JobFilter(FilterSet):
    event = django_filters.CharFilter(field_name='event', lookup_expr='slug')

    class Meta:
        model = BankImportJob
        fields = ['state', 'event']


class BankImportJobViewSet(CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = BankImportJobSerializer
    queryset = BankImportJob.objects.none()
    filter_backends = (DjangoFilterBackend,)
    filterset_class = JobFilter
    permission = 'can_view_orders'

    def get_queryset(self):
        return BankImportJob.objects.filter(organizer=self.request.organizer)

    def perform_create(self, serializer):
        return serializer.save()

    def create(self, request, *args, **kwargs):
        perm_holder = (request.auth if isinstance(request.auth, (Device, TeamAPIToken)) else request.user)
        if not perm_holder.has_organizer_permission(request.organizer, 'can_change_orders'):
            raise PermissionDenied('Invalid set of permissions')

        if BankImportJob.objects.filter(Q(organizer=request.organizer)).filter(
            state=BankImportJob.STATE_RUNNING,
            created__gte=now() - timedelta(minutes=30)  # safety timeout
        ).exists():
            return Response({'error': ['A job is currently running.']}, status=status.HTTP_409_CONFLICT)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = self.perform_create(serializer)
        process_banktransfers.apply_async(kwargs={
            'job': job.pk,
            'data': job._data
        })
        job.refresh_from_db()
        return Response(self.get_serializer(instance=job).data, status=status.HTTP_201_CREATED)

    def get_serializer(self, *args, **kwargs):
        kwargs['organizer'] = self.request.organizer
        return super().get_serializer(*args, **kwargs)
