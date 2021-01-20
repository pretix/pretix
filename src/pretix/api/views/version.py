from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from packaging import version
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from pretix import __version__
from pretix.api.auth.device import DeviceTokenAuthentication
from pretix.api.auth.permission import AnyAuthenticatedClientPermission
from pretix.api.auth.token import TeamTokenAuthentication


def numeric_version(v):
    # Converts a pretix version to a large int
    # e.g. 30060001000
    #      |--------------------- Major version
    #       |-|------------------ Minor version
    #          |-|--------------- Patch version
    #             ||------------- Stage (10 dev, 20 alpha, 30 beta, 40 rc, 50 release, 60 post)
    #               ||----------- Stage version (number of dev/alpha/beta/rc/post release)
    v = version.parse(v)
    phases = {
        'dev': 10,
        'a': 20,
        'b': 30,
        'rc': 40,
        'release': 50,
        'post': 60
    }
    vnum = 0

    if v.is_postrelease:
        vnum += v.post
        vnum += phases['post'] * 100
    elif v.dev is not None:
        vnum += v.dev
        vnum += phases['dev'] * 100
    elif v.is_prerelease and v.pre:
        vnum += v.pre[0]
        vnum += phases[v.pre[1]] * 100
    else:
        vnum += phases['release'] * 100
    for i, part in enumerate(reversed(v.release)):
        vnum += part * (1000 ** i) * 10000
    return vnum


class VersionView(APIView):
    authentication_classes = (
        SessionAuthentication, OAuth2Authentication, DeviceTokenAuthentication, TeamTokenAuthentication
    )
    permission_classes = [AnyAuthenticatedClientPermission]

    def get(self, request, format=None):
        return Response({
            'pretix': __version__,
            'pretix_numeric': numeric_version(__version__),
        })
