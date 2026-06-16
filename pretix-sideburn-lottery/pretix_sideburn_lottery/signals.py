from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import reverse

from pretix.base.email import SimpleFunctionalMailTextPlaceholder
from pretix.base.signals import register_mail_placeholders
from pretix.control.signals import waitinglist_index_html

from .services.rank import get_waiting_list_rank


@receiver(register_mail_placeholders, dispatch_uid="sideburn_lottery_waiting_list_position")
def register_waiting_list_position_placeholder(sender, **kwargs):
    return SimpleFunctionalMailTextPlaceholder(
        "waiting_list_position",
        ["waiting_list_entry"],
        lambda waiting_list_entry: (
            (lambda position: str(position) if position is not None else "")(
                get_waiting_list_rank(waiting_list_entry)
            )
        ),
        "42",
    )


@receiver(waitinglist_index_html, dispatch_uid="sideburn_lottery_waitinglist_index_html")
def render_waitinglist_lottery_actions(sender, request, **kwargs):
    template = get_template(
        "pretix_sideburn_lottery/fragment/waitinglist_lottery_actions.html"
    )
    kwargs = {
        "organizer": request.event.organizer.slug,
        "event": request.event.slug,
    }
    return template.render(
        {
            "request": request,
            "run_url": reverse("plugins:pretix_sideburn_lottery:run", kwargs=kwargs),
            "revert_url": reverse(
                "plugins:pretix_sideburn_lottery:revert", kwargs=kwargs
            ),
        },
        request=request,
    )
