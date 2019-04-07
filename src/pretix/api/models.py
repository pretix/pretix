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
from oauth2_provider.validators import URIValidator


class OAuthApplication(AbstractApplication):
    name = models.CharField(verbose_name=_("Application name"), max_length=255, blank=False)
    redirect_uris = models.TextField(
        blank=False, validators=[URIValidator],
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


class WebHook(models.Model):
    organizer = models.ForeignKey('pretixbase.Organizer', on_delete=models.CASCADE, related_name='webhooks')
    enabled = models.BooleanField(default=True, verbose_name=_("Enable webhook"))
    target_url = models.URLField(verbose_name=_("Target URL"))
    all_events = models.BooleanField(default=True, verbose_name=_("All events (including newly created ones)"))
    limit_events = models.ManyToManyField('pretixbase.Event', verbose_name=_("Limit to events"), blank=True)

    class Meta:
        ordering = ('id',)

    @property
    def action_types(self):
        return [
            l.action_type for l in self.listeners.all()
        ]


class WebHookEventListener(models.Model):
    webhook = models.ForeignKey('WebHook', on_delete=models.CASCADE, related_name='listeners')
    action_type = models.CharField(max_length=255)

    class Meta:
        ordering = ("action_type",)


class WebHookCall(models.Model):
    webhook = models.ForeignKey('WebHook', on_delete=models.CASCADE, related_name='calls')
    datetime = models.DateTimeField(auto_now_add=True)
    target_url = models.URLField()
    action_type = models.CharField(max_length=255)
    is_retry = models.BooleanField(default=False)
    execution_time = models.FloatField(null=True)
    return_code = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=False)
    payload = models.TextField()
    response_body = models.TextField()

    class Meta:
        ordering = ("-datetime",)


class ApiCall(models.Model):
    idempotency_key = models.CharField(max_length=190, db_index=True)
    auth_hash = models.CharField(max_length=190, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    locked = models.DateTimeField(null=True)

    request_method = models.CharField(max_length=20)
    request_path = models.CharField(max_length=255)

    response_code = models.PositiveIntegerField()
    response_headers = models.TextField()
    response_body = models.BinaryField()

    class Meta:
        unique_together = (('idempotency_key', 'auth_hash'),)
