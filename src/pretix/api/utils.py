from pretix.api.models import OAuthAccessToken
from pretix.base.models import Device, TeamAPIToken


def get_api_source(request):
    if isinstance(request.auth, Device):
        return "pretix.api", f"device:{request.auth.pk}"
    elif isinstance(request.auth, TeamAPIToken):
        return "pretix.api", f"token:{request.auth.pk}"
    elif isinstance(request.auth, OAuthAccessToken):
        return "pretix.api", f"oauth.app:{request.auth.application.pk}"
    elif request.user.is_authenticated:
        return "pretix.api", f"user:{request.user.pk}"
    return "pretix.api", None
