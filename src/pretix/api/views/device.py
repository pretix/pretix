import logging

from django.utils.timezone import now
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from pretix.api.auth.device import DeviceTokenAuthentication
from pretix.base.models import Device
from pretix.base.models.devices import generate_api_token

logger = logging.getLogger(__name__)


class InitializationRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=190)
    hardware_brand = serializers.CharField(max_length=190)
    hardware_model = serializers.CharField(max_length=190)
    software_brand = serializers.CharField(max_length=190)
    software_version = serializers.CharField(max_length=190)


class UpdateRequestSerializer(serializers.Serializer):
    hardware_brand = serializers.CharField(max_length=190)
    hardware_model = serializers.CharField(max_length=190)
    software_brand = serializers.CharField(max_length=190)
    software_version = serializers.CharField(max_length=190)


class DeviceSerializer(serializers.ModelSerializer):
    organizer = serializers.SlugRelatedField(slug_field='slug', read_only=True)

    class Meta:
        model = Device
        fields = [
            'organizer', 'device_id', 'unique_serial', 'api_token',
            'name',
        ]


class InitializeView(APIView):
    authentication_classes = tuple()
    permission_classes = tuple()

    def post(self, request, format=None):
        serializer = InitializationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            device = Device.objects.get(initialization_token=serializer.validated_data.get('token'))
        except Device.DoesNotExist:
            raise ValidationError({'token': ['Unknown initialization token.']})

        if device.initialized:
            raise ValidationError({'token': ['This initialization token has already been used.']})

        device.initialized = now()
        device.hardware_brand = serializer.validated_data.get('hardware_brand')
        device.hardware_model = serializer.validated_data.get('hardware_model')
        device.software_brand = serializer.validated_data.get('software_brand')
        device.software_version = serializer.validated_data.get('software_version')
        device.api_token = generate_api_token()
        device.save()

        device.log_action('pretix.device.initialized', data=serializer.validated_data, auth=device)

        serializer = DeviceSerializer(device)
        return Response(serializer.data)


class UpdateView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    def post(self, request, format=None):
        serializer = UpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = request.auth
        device.hardware_brand = serializer.validated_data.get('hardware_brand')
        device.hardware_model = serializer.validated_data.get('hardware_model')
        device.software_brand = serializer.validated_data.get('software_brand')
        device.software_version = serializer.validated_data.get('software_version')
        device.save()
        device.log_action('pretix.device.updated', data=serializer.validated_data, auth=device)

        serializer = DeviceSerializer(device)
        return Response(serializer.data)


class RollKeyView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    def post(self, request, format=None):
        device = request.auth
        device.api_token = generate_api_token()
        device.save()
        device.log_action('pretix.device.keyroll', auth=device)

        serializer = DeviceSerializer(device)
        return Response(serializer.data)


class RevokeKeyView(APIView):
    authentication_classes = (DeviceTokenAuthentication,)

    def post(self, request, format=None):
        device = request.auth
        device.revoked = True
        device.save()
        device.log_action('pretix.device.revoked', auth=device)

        serializer = DeviceSerializer(device)
        return Response(serializer.data)
