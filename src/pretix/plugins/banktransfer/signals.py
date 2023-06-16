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
from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _, gettext_noop
from i18nfield.strings import LazyI18nString

from pretix.base.signals import logentry_display, register_payment_providers
from pretix.control.signals import html_head, nav_event, nav_organizer

from ...base.settings import settings_hierarkey
from .payment import BankTransfer


@receiver(register_payment_providers, dispatch_uid="payment_banktransfer")
def register_payment_provider(sender, **kwargs):
    return BankTransfer


@receiver(nav_event, dispatch_uid="payment_banktransfer_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(request.organizer, request.event, 'can_change_orders', request=request):
        return []
    return [
        {
            'label': _("Bank transfer"),
            'url': reverse('plugins:banktransfer:import', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'icon': 'university',
            'children': [
                {
                    'label': _('Import bank data'),
                    'url': reverse('plugins:banktransfer:import', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:banktransfer' and url.url_name == 'import'),
                },
                {
                    'label': _('Export refunds'),
                    'url': reverse('plugins:banktransfer:refunds.list', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:banktransfer' and url.url_name.startswith("refunds")),
                },
            ]
        },
    ]


@receiver(nav_organizer, dispatch_uid="payment_banktransfer_organav")
def control_nav_orga_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_organizer_permission(request.organizer, 'can_change_orders', request=request):
        return []
    if not request.organizer.events.filter(plugins__icontains='pretix.plugins.banktransfer'):
        return []
    return [
        {
            'label': _("Bank transfer"),
            'url': reverse('plugins:banktransfer:import', kwargs={
                'organizer': request.organizer.slug,
            }),
            'icon': 'university',
            'children': [
                {
                    'label': _('Import bank data'),
                    'url': reverse('plugins:banktransfer:import', kwargs={
                        'organizer': request.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:banktransfer' and url.url_name == 'import'),
                    'icon': 'upload',
                },
                {
                    'label': _('Export refunds'),
                    'url': reverse('plugins:banktransfer:refunds.list', kwargs={
                        'organizer': request.organizer.slug,
                    }),
                    'active': (url.namespace == 'plugins:banktransfer' and url.url_name.startswith("refunds")),
                },
            ]
        }
    ]


@receiver(html_head, dispatch_uid="banktransfer_html_head")
def html_head_presale(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    if url.namespace == 'plugins:banktransfer':
        template = get_template('pretixplugins/banktransfer/control_head.html')
        return template.render({})
    else:
        return ""


@receiver(signal=logentry_display)
def pretixcontrol_logentry_display(sender, logentry, **kwargs):
    plains = {
        'pretix.plugins.banktransfer.order.email.invoice': _('The invoice was sent to the designated email address.'),
    }
    if logentry.action_type in plains:
        return plains[logentry.action_type]


settings_hierarkey.add_default(
    'payment_banktransfer_invoice_email_subject',
    default_type=LazyI18nString,
    value=LazyI18nString.from_gettext(gettext_noop("Invoice {invoice_number}"))
)
settings_hierarkey.add_default(
    'payment_banktransfer_invoice_email_text',
    default_type=LazyI18nString,
    value=LazyI18nString.from_gettext(gettext_noop("""Hello,

you receive this message because an order for {event} was placed by {order_email} and we have been asked to forward the invoice to you.

Best regards,  

Your {event} team"""))  # noqa: W291
)
