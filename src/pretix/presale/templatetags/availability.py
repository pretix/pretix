from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.signals import sold_out_availability

register = template.Library()


def _default_sold_out_html(event, item, variation, allow_waitinglist, cart_namespace, subevent, compact):
    if compact:
        label = format_html('<strong class="gone">{}</strong>', _("SOLD OUT"))
        if allow_waitinglist and item.allow_waitinglist:
            label += format_html("<br/>{}", _("Waiting list"))
        return label

    label = format_html("<strong>{}</strong>", _("SOLD OUT"))
    if allow_waitinglist and item.allow_waitinglist:
        kwargs = {"cart_namespace": cart_namespace or ""}
        query = f"?item={item.pk}"
        if variation:
            query += f"&var={variation.pk}"
        if subevent:
            query += f"&subevent={subevent.pk}"
        url = eventreverse(event, "presale:event.waitinglist", kwargs=kwargs) + query
        label += format_html(
            '<br/><a href="{}">'
            '<span class="fa fa-plus-circle" aria-hidden="true"></span> {}'
            "</a>",
            url,
            _("Waiting list"),
        )
    return label


@register.simple_tag(takes_context=True)
def sold_out_availability_tag(context, event, item, var=None, compact=False):
    variation = var if var and var != 0 else None
    allow_waitinglist = context.get("allow_waitinglist", False)
    cart_namespace = context.get("cart_namespace")
    subevent = context.get("subevent")

    for receiver, response in sold_out_availability.send(
        event,
        item=item,
        variation=variation,
        allow_waitinglist=allow_waitinglist,
        cart_namespace=cart_namespace,
        subevent=subevent,
        compact=compact,
    ):
        if response:
            return mark_safe(response)

    return _default_sold_out_html(
        event, item, variation, allow_waitinglist, cart_namespace, subevent, compact
    )
