#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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
from django.utils.translation import gettext_lazy as _
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer


class KnownDomain(models.Model):
    domainname = models.CharField(max_length=255, primary_key=True)
    organizer = models.ForeignKey(Organizer, blank=True, null=True, related_name='domains', on_delete=models.CASCADE)
    event = models.ForeignKey(Event, blank=True, null=True, related_name='domains', on_delete=models.PROTECT)

    class Meta:
        verbose_name = _("Known domain")
        verbose_name_plural = _("Known domains")

    def __str__(self):
        return self.domainname

    @scopes_disabled()
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.event:
            self.event.get_cache().clear()
        elif self.organizer:
            self.organizer.get_cache().clear()
            for event in self.organizer.events.all():
                event.get_cache().clear()
        cache.delete('pretix_multidomain_organizer_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_instance_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_event_{}'.format(self.domainname))

    @scopes_disabled()
    def delete(self, *args, **kwargs):
        if self.event:
            self.event.get_cache().clear()
        elif self.organizer:
            self.organizer.get_cache().clear()
            for event in self.organizer.events.all():
                event.get_cache().clear()
        cache.delete('pretix_multidomain_organizer_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_instance_{}'.format(self.domainname))
        cache.delete('pretix_multidomain_event_{}'.format(self.domainname))
        super().delete(*args, **kwargs)
