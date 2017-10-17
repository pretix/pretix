from django.core.cache import cache
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
        cache.delete('pretix_multidomain_organizer_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_organizer_instance_{}'.format(self.domainname))

    def delete(self, *args, **kwargs):
        if self.organizer:
            self.organizer.get_cache().clear()
        cache.delete('pretix_multidomain_organizer_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_organizer_instance_{}'.format(self.domainname))
        super().delete(*args, **kwargs)
