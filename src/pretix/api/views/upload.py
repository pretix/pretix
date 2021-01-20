import datetime

from django.utils.timezone import now
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView

from pretix.api.auth.device import DeviceTokenAuthentication
from pretix.api.auth.permission import AnyAuthenticatedClientPermission
from pretix.api.auth.token import TeamTokenAuthentication
from pretix.base.models import CachedFile

ALLOWED_TYPES = {
    'image/gif': {'.gif'},
    'image/jpeg': {'.jpg', '.jpeg'},
    'image/png': {'.png'},
    'application/pdf': {'.pdf'},
}


class UploadView(APIView):
    authentication_classes = (
        SessionAuthentication, OAuth2Authentication, DeviceTokenAuthentication, TeamTokenAuthentication
    )
    parser_classes = [FileUploadParser]
    permission_classes = [AnyAuthenticatedClientPermission]

    def post(self, request):
        if 'file' not in request.data:
            raise ValidationError('No file has been submitted.')
        file_obj = request.data['file']
        content_type = file_obj.content_type.split(";")[0]  # ignore e.g. "; charset=…"
        if content_type not in ALLOWED_TYPES:
            raise ValidationError('Content type "{type}" is not allowed'.format(type=content_type))
        if not any(file_obj.name.endswith(ext) for ext in ALLOWED_TYPES[content_type]):
            raise ValidationError('File name "{name}" has an invalid extension for type "{type}"'.format(
                name=file_obj.name,
                type=content_type
            ))
        cf = CachedFile.objects.create(
            expires=now() + datetime.timedelta(days=1),
            date=now(),
            web_download=False,
            filename=file_obj.name,
            type=content_type,
            session_key=f'api-upload-{str(type(request.user or request.auth))}-{(request.user or request.auth).pk}'
        )
        cf.file.save(file_obj.name, file_obj)
        cf.save()
        return Response({
            'id': f'file:{cf.pk}'
        }, status=201)
