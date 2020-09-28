from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from pretix.api.auth.permission import ProfilePermission


class MeView(APIView):
    authentication_classes = (SessionAuthentication, OAuth2Authentication)
    permission_classes = (ProfilePermission,)

    def get(self, request, format=None):
        return Response({
            'email': request.user.email,
            'fullname': request.user.fullname,
            'locale': request.user.locale,
            'is_staff': request.user.is_staff,
            'timezone': request.user.timezone
        })
