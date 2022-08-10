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
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.dispatch import receiver
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import CachedCombinedTicket, CachedTicket
from pretix.base.models.customers import CustomerSSOGrant

from ..models import CachedFile, CartPosition, InvoiceAddress
from ..signals import periodic_task


@receiver(signal=periodic_task)
@scopes_disabled()
def clean_cart_positions(sender, **kwargs):
    for cp in CartPosition.objects.filter(expires__lt=now() - timedelta(days=14), addon_to__isnull=False):
        cp.delete()
    for cp in CartPosition.objects.filter(expires__lt=now() - timedelta(days=14), addon_to__isnull=True):
        cp.delete()
    for ia in InvoiceAddress.objects.filter(order__isnull=True, customer__isnull=True, last_modified__lt=now() - timedelta(days=14)):
        ia.delete()


@receiver(signal=periodic_task)
@scopes_disabled()
def clean_cached_files(sender, **kwargs):
    for cf in CachedFile.objects.filter(expires__isnull=False, expires__lt=now()):
        cf.delete()


@receiver(signal=periodic_task)
@scopes_disabled()
def clean_cached_tickets(sender, **kwargs):
    for cf in CachedTicket.objects.filter(created__lte=now() - timedelta(hours=settings.CACHE_TICKETS_HOURS)):
        cf.delete()
    for cf in CachedCombinedTicket.objects.filter(created__lte=now() - timedelta(hours=settings.CACHE_TICKETS_HOURS)):
        cf.delete()
    for cf in CachedTicket.objects.filter(created__lte=now() - timedelta(minutes=30), file__isnull=True):
        cf.delete()
    for cf in CachedCombinedTicket.objects.filter(created__lte=now() - timedelta(minutes=30), file__isnull=True):
        cf.delete()


@receiver(signal=periodic_task)
@scopes_disabled()
def clearsessions(sender, **kwargs):
    call_command('clearsessions')


@receiver(signal=periodic_task)
@scopes_disabled()
def clear_oidc_data(sender, **kwargs):
    CustomerSSOGrant.objects.filter(expires__lt=now() - timedelta(days=14)).delete()
