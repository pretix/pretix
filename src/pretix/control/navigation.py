from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import pgettext_lazy, ugettext_lazy as _

from pretix.control.signals import (
    nav_event, nav_event_settings, nav_global, nav_organizer,
)


def get_event_navigation(request: HttpRequest):
    url = request.resolver_match
    nav = [
        {
            'label': _('Dashboard'),
            'url': reverse('control:event.index', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': (url.url_name == 'event.index'),
            'icon': 'dashboard',
        }
    ]
    if 'can_change_event_settings' in request.eventpermset:
        event_settings = [
            {
                'label': _('General'),
                'url': reverse('control:event.settings', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings',
            },
            {
                'label': _('Payment'),
                'url': reverse('control:event.settings.payment', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings.payment',
            },
            {
                'label': _('Plugins'),
                'url': reverse('control:event.settings.plugins', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings.plugins',
            },
            {
                'label': _('Display'),
                'url': reverse('control:event.settings.display', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings.display',
            },
            {
                'label': _('Tickets'),
                'url': reverse('control:event.settings.tickets', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings.tickets',
            },
            {
                'label': _('E-mail'),
                'url': reverse('control:event.settings.mail', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings.mail',
            },
            {
                'label': _('Tax rules'),
                'url': reverse('control:event.settings.tax', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings.tax',
            },
            {
                'label': _('Invoicing'),
                'url': reverse('control:event.settings.invoice', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings.invoice',
            },
            {
                'label': _('Widget'),
                'url': reverse('control:event.settings.widget', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': url.url_name == 'event.settings.widget',
            },
        ]
        event_settings += sorted(
            sum((list(a[1]) for a in nav_event_settings.send(request.event, request=request)), []),
            key=lambda r: r['label']
        )
        nav.append({
            'label': _('Settings'),
            'url': reverse('control:event.settings', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': False,
            'icon': 'wrench',
            'children': event_settings
        })
        if request.event.has_subevents:
            nav.append({
                'label': pgettext_lazy('subevent', 'Dates'),
                'url': reverse('control:event.subevents', kwargs={
                    'event': request.event.slug,
                    'organizer': request.event.organizer.slug,
                }),
                'active': ('event.subevent' in url.url_name),
                'icon': 'calendar',
            })

    if 'can_change_items' in request.eventpermset:
        nav.append({
            'label': _('Products'),
            'url': reverse('control:event.items', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': False,
            'icon': 'ticket',
            'children': [
                {
                    'label': _('Products'),
                    'url': reverse('control:event.items', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': url.url_name in (
                        'event.item', 'event.items.add', 'event.items') or "event.item." in url.url_name,
                },
                {
                    'label': _('Quotas'),
                    'url': reverse('control:event.items.quotas', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.items.quota' in url.url_name,
                },
                {
                    'label': _('Categories'),
                    'url': reverse('control:event.items.categories', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.items.categories' in url.url_name,
                },
                {
                    'label': _('Questions'),
                    'url': reverse('control:event.items.questions', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.items.questions' in url.url_name,
                },
            ]
        })

    if 'can_view_orders' in request.eventpermset:
        nav.append({
            'label': _('Orders'),
            'url': reverse('control:event.orders', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': False,
            'icon': 'shopping-cart',
            'children': [
                {
                    'label': _('All orders'),
                    'url': reverse('control:event.orders', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': url.url_name in ('event.orders', 'event.order') or "event.order." in url.url_name,
                },
                {
                    'label': _('Overview'),
                    'url': reverse('control:event.orders.overview', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.orders.overview' in url.url_name,
                },
                {
                    'label': _('Refunds'),
                    'url': reverse('control:event.orders.refunds', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.orders.refunds' in url.url_name,
                },
                {
                    'label': _('Export'),
                    'url': reverse('control:event.orders.export', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.orders.export' in url.url_name,
                },
                {
                    'label': _('Waiting list'),
                    'url': reverse('control:event.orders.waitinglist', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.orders.waitinglist' in url.url_name,
                },
            ]
        })

    if 'can_view_vouchers' in request.eventpermset:
        nav.append({
            'label': _('Vouchers'),
            'url': reverse('control:event.vouchers', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': False,
            'icon': 'tags',
            'children': [
                {
                    'label': _('All vouchers'),
                    'url': reverse('control:event.vouchers', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': url.url_name != 'event.vouchers.tags' and "event.vouchers" in url.url_name,
                },
                {
                    'label': _('Tags'),
                    'url': reverse('control:event.vouchers.tags', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.vouchers.tags' in url.url_name,
                },
            ]
        })

    if 'can_view_orders' in request.eventpermset:
        nav.append({
            'label': pgettext_lazy('navigation', 'Check-in'),
            'url': reverse('control:event.orders.checkinlists', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': False,
            'icon': 'check-square-o',
            'children': [
                {
                    'label': _('Check-in lists'),
                    'url': reverse('control:event.orders.checkinlists', kwargs={
                        'event': request.event.slug,
                        'organizer': request.event.organizer.slug,
                    }),
                    'active': 'event.orders.checkin' in url.url_name,
                },
            ]
        })

    merge_in(nav, sorted(
        sum((list(a[1]) for a in nav_event.send(request.event, request=request)), []),
        key=lambda r: r['label']
    ))

    return nav


def get_global_navigation(request):
    url = request.resolver_match
    has_staff_session = request.user.has_active_staff_session(request.session.session_key)
    nav = [
        {
            'label': _('Dashboard'),
            'url': reverse('control:index'),
            'active': (url.url_name == 'index'),
            'icon': 'dashboard',
        },
        {
            'label': _('Events'),
            'url': reverse('control:events'),
            'active': 'events' in url.url_name,
            'icon': 'calendar',
        },
        {
            'label': _('Organizers'),
            'url': reverse('control:organizers'),
            'active': 'organizers' in url.url_name,
            'icon': 'group',
        },
        {
            'label': _('Order search'),
            'url': reverse('control:search.orders'),
            'active': 'search.orders' in url.url_name,
            'icon': 'search',
        },
        {
            'label': _('User settings'),
            'url': reverse('control:user.settings'),
            'active': False,
            'icon': 'user',
            'children': [
                {
                    'label': _('General'),
                    'url': reverse('control:user.settings'),
                    'active': 'user.settings' == url.url_name,
                },
                {
                    'label': _('Notifications'),
                    'url': reverse('control:user.settings.notifications'),
                    'active': 'user.settings.notifications' == url.url_name,
                },
                {
                    'label': _('2FA'),
                    'url': reverse('control:user.settings.2fa'),
                    'active': 'user.settings.2fa' in url.url_name,
                },
                {
                    'label': _('Authorized apps'),
                    'url': reverse('control:user.settings.oauth.list'),
                    'active': 'user.settings.oauth' in url.url_name,
                },
                {
                    'label': _('Account history'),
                    'url': reverse('control:user.settings.history'),
                    'active': 'user.settings.history' in url.url_name,
                },
            ]
        },
    ]
    if has_staff_session:
        nav.append({
            'label': _('Users'),
            'url': reverse('control:users'),
            'active': False,
            'icon': 'user',
            'children': [
                {
                    'label': _('All users'),
                    'url': reverse('control:users'),
                    'active': ('users' in url.url_name),
                },
                {
                    'label': _('Admin sessions'),
                    'url': reverse('control:user.sudo.list'),
                    'active': ('sudo' in url.url_name),
                },
            ]
        })
        nav.append({
            'label': _('Global settings'),
            'url': reverse('control:global.settings'),
            'active': False,
            'icon': 'wrench',
            'children': [
                {
                    'label': _('Settings'),
                    'url': reverse('control:global.settings'),
                    'active': (url.url_name == 'global.settings'),
                },
                {
                    'label': _('Update check'),
                    'url': reverse('control:global.update'),
                    'active': (url.url_name == 'global.update'),
                },
            ]
        })

    merge_in(nav, sorted(
        sum((list(a[1]) for a in nav_global.send(request, request=request)), []),
        key=lambda r: r['label']
    ))
    return nav


def get_organizer_navigation(request):
    url = request.resolver_match
    nav = [
        {
            'label': _('Events'),
            'url': reverse('control:organizer', kwargs={
                'organizer': request.organizer.slug
            }),
            'active': url.url_name == 'organizer',
            'icon': 'calendar',
        },
    ]
    if 'can_change_organizer_settings' in request.orgapermset:
        nav.append({
            'label': _('Settings'),
            'url': reverse('control:organizer.edit', kwargs={
                'organizer': request.organizer.slug
            }),
            'icon': 'wrench',
            'children': [
                {
                    'label': _('General'),
                    'url': reverse('control:organizer.edit', kwargs={
                        'organizer': request.organizer.slug
                    }),
                    'active': url.url_name == 'organizer.edit',
                },
                {
                    'label': _('Display'),
                    'url': reverse('control:organizer.display', kwargs={
                        'organizer': request.organizer.slug
                    }),
                    'active': url.url_name == 'organizer.display',
                },
            ]
        })
    if 'can_change_teams' in request.orgapermset:
        nav.append({
            'label': _('Teams'),
            'url': reverse('control:organizer.teams', kwargs={
                'organizer': request.organizer.slug
            }),
            'active': 'organizer.team' in url.url_name,
            'icon': 'group',
        })
    if 'can_change_organizer_settings' in request.orgapermset:
        nav.append({
            'label': _('Devices'),
            'url': reverse('control:organizer.devices', kwargs={
                'organizer': request.organizer.slug
            }),
            'active': 'organizer.device' in url.url_name,
            'icon': 'group',
        })
        nav.append({
            'label': _('Webhooks'),
            'url': reverse('control:organizer.webhooks', kwargs={
                'organizer': request.organizer.slug
            }),
            'active': 'organizer.webhook' in url.url_name,
            'icon': 'group',
        })

    merge_in(nav, sorted(
        sum((list(a[1]) for a in nav_organizer.send(request.organizer, request=request, organizer=request.organizer)),
            []),
        key=lambda r: r['label']
    ))
    return nav


def merge_in(nav, newnav):
    for item in newnav:
        if 'parent' in item:
            parents = [n for n in nav if n['url'] == item['parent']]
            if parents:
                parents[0]['children'].append(item)
        else:
            nav.append(item)
