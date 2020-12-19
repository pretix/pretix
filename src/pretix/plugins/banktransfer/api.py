from datetime import timedelta

import django_filters
from django.db.models import Q
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
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
                  'comment', 'iban', 'bic')


class BankImportJobSerializer(serializers.ModelSerializer):
    event = serializers.SlugRelatedField(slug_field='slug', read_only=True, allow_null=True)
    transactions = BankTransactionSerializer(many=True, read_only=False)
    state = serializers.CharField(read_only=True)
    partial = False

    class Meta:
        model = BankImportJob
        fields = ('id', 'event', 'created', 'state', 'transactions')

    def __init__(self, *args, **kwargs):
        self.organizer = kwargs.pop('organizer')
        self.fields['event'].read_only = False
        self.fields['event'].queryset = self.organizer.events.all()
        super().__init__(*args, **kwargs)

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
            created__lte=now() - timedelta(minutes=30)  # safety timeout
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
