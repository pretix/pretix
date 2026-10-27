import datetime
import logging

from django.contrib.auth.models import AnonymousUser
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.http import condition
from rest_framework import exceptions, permissions, serializers
from rest_framework.authentication import (
    BaseAuthentication, get_authorization_header,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from pretix.helpers.http import ChunkBasedFileResponse
from pretix.plugins.wallet.models import AppleWalletDevice, AppleWalletPass

logger = logging.getLogger("pretix.plugins.wallet.apple")


class ApplePassAuthentication(BaseAuthentication):
    keyword = "ApplePass"
    model = AppleWalletPass

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) == 1:
            msg = _("Invalid token header. No credentials provided.")
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _("Invalid token header. Token string should not contain spaces.")
            raise exceptions.AuthenticationFailed(msg)

        try:
            token = auth[1].decode()
        except UnicodeError:
            msg = _(
                "Invalid token header. Token string should not contain invalid characters."
            )
            raise exceptions.AuthenticationFailed(msg)

        try:
            pass_obj = AppleWalletPass.objects.get(
                token=token, order_position__order__event=request.event
            )
        except AppleWalletPass.DoesNotExist:
            raise exceptions.AuthenticationFailed(_("Invalid token."))

        return (AnonymousUser(), pass_obj)

    def authenticate_header(self, request):
        return self.keyword


class ApplePassPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not isinstance(request.auth, AppleWalletPass):
            return False
        pass_obj = request.auth
        if pass_obj.serial_number != view.kwargs["serial_number"]:
            return False
        if (
            request.event.settings.wallet_apple_pass_type_id
            != view.kwargs["pass_type_identifier"]
        ):
            return False

        return True


class RegisterPassSerializer(serializers.Serializer):
    push_token = serializers.CharField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["push_token"].field_name = "pushToken"


class LogEntrySerializer(serializers.Serializer):
    logs = serializers.ListField()


class DeviceRegistrationView(APIView):
    authentication_classes = [ApplePassAuthentication]
    permission_classes = [ApplePassPermission]

    def post(self, request, *args, device_library_identifier, **kwargs):
        serializer = RegisterPassSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device, _ = AppleWalletDevice.objects.get_or_create(
            device_library_id=device_library_identifier,
            defaults={"push_token": serializer.data["pushToken"]},
        )
        device.passes.add(request.auth)
        return Response({})

    def delete(self, request, *args, device_library_identifier, **kwargs):
        try:
            device = AppleWalletDevice.objects.get(
                device_library_id=device_library_identifier,
            )
        except AppleWalletDevice.DoesNotExist:
            raise exceptions.NotFound(_("Unknown device library identifier."))
        device.passes.remove(request.auth)
        if not device.passes.exists():
            device.delete()
        # TODO: also delete pass if no devices are registered anymore?
        return Response({})


class DeviceGetUpdatablePassesView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(
        self, request, *args, device_library_identifier, pass_type_identifier, **kwargs
    ):
        try:
            device = AppleWalletDevice.objects.get(
                device_library_id=device_library_identifier,
            )
        except AppleWalletDevice.DoesNotExist:
            raise exceptions.NotFound(_("Unknown device library identifier."))

        passes = device.passes.filter(pass_type=pass_type_identifier)
        try:
            last_update = datetime.datetime.fromtimestamp(int(request.GET.get("passesUpdatedSince", 0)), datetime.UTC)
            passes = passes.filter(
                updated_at__gt=last_update
            )
        except ValueError:
            pass

        return Response(
            {
                "serialNumbers": passes.values_list("serial_number", flat=True),
                "lastUpdated": str(int(datetime.datetime.now(datetime.UTC).timestamp())),
            }
        )


class GetPassView(APIView):
    authentication_classes = [ApplePassAuthentication]
    permission_classes = [ApplePassPermission]

    @method_decorator(
        condition(
            last_modified_func=lambda request, *args, **kwargs: request.auth.updated_at
        )
    )
    def get(self, request, *args, **kwargs):
        resp = ChunkBasedFileResponse(request.auth.content)
        resp["Content-Type"] = "application/vnd.apple.pkpass"
        return resp


class LogView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request, *args, **kwargs):
        serializer = LogEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        logger.debug("Received apple wallet log messages: %s", serializer.data["logs"])
        return Response({})
