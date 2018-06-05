from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from oauth2_provider.generators import (
    generate_client_id, generate_client_secret,
)
from oauth2_provider.models import (
    AbstractAccessToken, AbstractApplication, AbstractGrant,
    AbstractRefreshToken,
)
from oauth2_provider.validators import validate_uris


class OAuthApplication(AbstractApplication):
    name = models.CharField(verbose_name=_("Application name"), max_length=255, blank=False)
    redirect_uris = models.TextField(
        blank=False, validators=[validate_uris],
        verbose_name=_("Redirection URIs"),
        help_text=_("Allowed URIs list, space separated")
    )
    client_id = models.CharField(
        verbose_name=_("Client ID"),
        max_length=100, unique=True, default=generate_client_id, db_index=True
    )
    client_secret = models.CharField(
        verbose_name=_("Client secret"),
        max_length=255, blank=False, default=generate_client_secret, db_index=True
    )
    active = models.BooleanField(default=True)

    def get_absolute_url(self):
        return reverse("control:user.settings.oauth.app", kwargs={'pk': self.id})

    def is_usable(self, request):
        return self.active and super().is_usable(request)


class OAuthGrant(AbstractGrant):
    application = models.ForeignKey(
        OAuthApplication, on_delete=models.CASCADE
    )
    organizers = models.ManyToManyField('pretixbase.Organizer')


class OAuthAccessToken(AbstractAccessToken):
    source_refresh_token = models.OneToOneField(
        # unique=True implied by the OneToOneField
        'OAuthRefreshToken', on_delete=models.SET_NULL, blank=True, null=True,
        related_name="refreshed_access_token"
    )
    application = models.ForeignKey(
        OAuthApplication, on_delete=models.CASCADE, blank=True, null=True,
    )
    organizers = models.ManyToManyField('pretixbase.Organizer')

    def revoke(self):
        self.expires = now() - timedelta(hours=1)
        self.save(update_fields=['expires'])


class OAuthRefreshToken(AbstractRefreshToken):
    application = models.ForeignKey(
        OAuthApplication, on_delete=models.CASCADE)
    access_token = models.OneToOneField(
        OAuthAccessToken, on_delete=models.SET_NULL, blank=True, null=True,
        related_name="refresh_token"
    )
