#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer


class KnownDomain(models.Model):
    MODE_ORG_DOMAIN = "organizer"
    MODE_ORG_ALT_DOMAIN = "organizer_alternative"
    MODE_EVENT_DOMAIN = "event"
    MODES = (
        (MODE_ORG_DOMAIN, _("Organizer domain")),
        (MODE_ORG_ALT_DOMAIN, _("Alternative organizer domain for a set of events")),
        (MODE_EVENT_DOMAIN, _("Event domain")),
    )

    domainname = models.CharField(
        max_length=255,
        primary_key=True,
        verbose_name=_("Domain name"),
    )
    mode = models.CharField(
        max_length=255,
        choices=MODES,
        default=MODE_ORG_DOMAIN,
        verbose_name=_("Mode"),
    )
    organizer = models.ForeignKey(
        Organizer,
        blank=True,
        null=True,
        related_name='domains',
        on_delete=models.CASCADE
    )
    event = models.OneToOneField(
        Event,
        blank=True,
        null=True,
        related_name='domain',
        on_delete=models.PROTECT,
        verbose_name=_("Event"),
    )

    class Meta:
        verbose_name = _("Known domain")
        verbose_name_plural = _("Known domains")
        constraints = [
            models.UniqueConstraint(
                fields=("organizer",),
                name="unique_organizer_domain",
                condition=Q(mode="organizer"),
            ),
        ]
        ordering = ("-mode", "domainname")

    def __str__(self):
        return self.domainname

    @scopes_disabled()
    def save(self, *args, **kwargs):
        if self.event:
            self.mode = KnownDomain.MODE_EVENT_DOMAIN
        elif self.mode == KnownDomain.MODE_EVENT_DOMAIN:
            raise ValueError("Event domain needs event")
        super().save(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()
            try:
                self.event.alternative_domain_assignment.delete()
            except AlternativeDomainAssignment.DoesNotExist:
                pass
        elif self.organizer:
            self.organizer.get_cache().clear()
            for event in self.organizer.events.all():
                event.get_cache().clear()
        cache.delete('pretix_multidomain_organizer_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_instances_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_event_{}'.format(self.domainname))

    @scopes_disabled()
    def delete(self, *args, **kwargs):
        if self.event:
            self.event.cache.clear()
        elif self.organizer:
            self.organizer.cache.clear()
            for event in self.organizer.events.all():
                event.cache.clear()
        cache.delete('pretix_multidomain_organizer_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_instances_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_event_{}'.format(self.domainname))
        super().delete(*args, **kwargs)

    def _log_domain_action(self, user, data):
        if self.event:
            self.event.log_action(
                'pretix.event.settings',
                user=user,
                data=data
            )
        else:
            self.organizer.log_action(
                'pretix.organizer.settings',
                user=user,
                data=data
            )

    def log_create(self, user):
        self._log_domain_action(user, {'add_alt_domain': self.domainname} if self.mode == KnownDomain.MODE_ORG_ALT_DOMAIN else {'domain': self.domainname})

    def log_delete(self, user):
        self._log_domain_action(user, {'remove_alt_domain': self.domainname} if self.mode == KnownDomain.MODE_ORG_ALT_DOMAIN else {'domain': None})


class AlternativeDomainAssignment(models.Model):
    domain = models.ForeignKey(
        KnownDomain,
        on_delete=models.CASCADE,
        related_name="event_assignments",
    )
    event = models.OneToOneField(
        Event,
        related_name="alternative_domain_assignment",
        on_delete=models.CASCADE,
    )

    @scopes_disabled()
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.event.cache.clear()
        cache.delete('pretix_multidomain_instances_{}'.format(self.domain_id))
        cache.delete('pretix_multidomain_event_{}'.format(self.domain_id))

    @scopes_disabled()
    def delete(self, *args, **kwargs):
        self.event.cache.clear()
        cache.delete('pretix_multidomain_instances_{}'.format(self.domain_id))
        cache.delete('pretix_multidomain_event_{}'.format(self.domain_id))
        super().delete(*args, **kwargs)
