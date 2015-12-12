from django.db import models
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Organizer


class KnownDomain(models.Model):
    domainname = models.CharField(max_length=255, primary_key=True)
    organizer = models.ForeignKey(Organizer, blank=True, null=True, related_name='domains')

    class Meta:
        verbose_name = _("Known domain")
        verbose_name_plural = _("Known domains")

    def __str__(self):
        return self.domainname

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.organizer:
            self.organizer.get_cache().clear()

    def delete(self, *args, **kwargs):
        if self.organizer:
            self.organizer.get_cache().clear()
        super().delete(*args, **kwargs)
