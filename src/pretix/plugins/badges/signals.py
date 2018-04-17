import copy

from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import ugettext_lazy as _

from pretix.base.signals import event_copy_data, item_copy_data
from pretix.control.signals import item_forms, nav_event
from pretix.plugins.badges.forms import BadgeItemForm
from pretix.plugins.badges.models import BadgeItem


@receiver(nav_event, dispatch_uid="badges_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    p = (
        request.user.has_event_permission(request.organizer, request.event, 'can_change_settings')
        or request.user.has_event_permission(request.organizer, request.event, 'can_view_orders')
    )
    if not p:
        return []
    return [
        {
            'label': _('Badges'),
            'url': reverse('plugins:badges:index', kwargs={
                'event': request.event.slug,
                'organizer': request.event.organizer.slug,
            }),
            'active': url.namespace == 'plugins:badges',
            'icon': 'id-card',
        }
    ]


@receiver(item_forms, dispatch_uid="badges_item_forms")
def control_item_forms(sender, request, item, **kwargs):
    try:
        inst = BadgeItem.objects.get(item=item)
    except BadgeItem.DoesNotExist:
        inst = BadgeItem(item=item)
    return BadgeItemForm(
        instance=inst,
        event=sender,
        data=(request.POST if request.method == "POST" else None),
        prefix="badgeitem"
    )


@receiver(item_copy_data, dispatch_uid="badges_item_copy")
def copy_item(sender, source, target, **kwargs):
    try:
        inst = BadgeItem.objects.get(item=source)
        BadgeItem.objects.create(item=target, layout=inst.layout)
    except BadgeItem.DoesNotExist:
        pass


@receiver(signal=event_copy_data, dispatch_uid="badges_copy_data")
def event_copy_data_receiver(sender, other, item_map, **kwargs):
    layout_map = {}
    for bl in other.badge_layouts.all():
        oldid = bl.pk
        bl = copy.copy(bl)
        bl.pk = None
        bl.event = sender
        bl.save()
        layout_map[oldid] = bl

    for bi in BadgeItem.objects.filter(item__event=other):
        BadgeItem.objects.create(item=item_map.get(bi.item_id), layout=layout_map.get(bi.layout_id))
