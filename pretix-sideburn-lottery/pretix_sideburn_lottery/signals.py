from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import reverse
from i18nfield.strings import LazyI18nString

from pretix.base.email import SimpleFunctionalMailTextPlaceholder
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    register_mail_placeholders,
    waiting_list_send_voucher,
    waitinglist_entry_created,
    waitinglist_entry_validate,
)
from pretix.control.signals import waitinglist_index_html
from pretix.presale.signals import (
    checkout_questions_top,
    front_page_bottom,
    sold_out_availability,
    waitinglist_template_name,
)

from .services.presale import get_sold_out_label
from .services.rank import get_waiting_list_rank
from .services.waitinglist import (
    DEFAULT_MAIL_TEXT_WAITING_LIST_CONFIRM,
    send_signup_confirmation,
    validate_no_active_voucher_duplicate,
)
from .views.presale import get_waiting_list_ranks

settings_hierarkey.add_default(
    "mail_text_waiting_list_confirm",
    LazyI18nString.from_gettext(DEFAULT_MAIL_TEXT_WAITING_LIST_CONFIRM),
    LazyI18nString,
)


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


@receiver(front_page_bottom, dispatch_uid="sideburn_lottery_front_page_rank")
def render_waiting_list_rank(sender, request, subevent=None, **kwargs):
    if not getattr(request, "customer", None):
        return ""
    event = sender
    if not event.settings.waiting_list_enabled:
        return ""
    ev = subevent or event
    if not ev.presale_is_running:
        return ""

    template = get_template(
        "pretix_sideburn_lottery/fragment/waitinglist_rank.html"
    )
    return template.render(
        {
            "request": request,
            "waiting_list_ranks": get_waiting_list_ranks(
                event, request.customer.email
            ),
        },
        request=request,
    )


@receiver(waitinglist_template_name, dispatch_uid="sideburn_lottery_waitinglist_template")
def provide_waitinglist_template(sender, **kwargs):
    return "pretix_sideburn_lottery/waitinglist.html"


@receiver(sold_out_availability, dispatch_uid="sideburn_lottery_sold_out_availability")
def render_sold_out_availability(
    sender,
    item,
    variation=None,
    allow_waitinglist=False,
    cart_namespace=None,
    subevent=None,
    compact=False,
    **kwargs,
):
    template = get_template(
        "pretix_sideburn_lottery/fragment/sold_out_availability.html"
    )
    return template.render(
        {
            "event": sender,
            "item": item,
            "variation": variation,
            "allow_waitinglist": allow_waitinglist,
            "cart_namespace": cart_namespace,
            "subevent": subevent,
            "compact": compact,
            "sold_out_label": get_sold_out_label(sender, item.pk),
        }
    )


@receiver(checkout_questions_top, dispatch_uid="sideburn_lottery_checkout_waiver")
def render_checkout_waiver(sender, request, **kwargs):
    template = get_template(
        "pretix_sideburn_lottery/fragment/checkout_waiver.html"
    )
    return template.render({"request": request}, request=request)


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


@receiver(waitinglist_entry_created, dispatch_uid="sideburn_lottery_signup_confirm")
def send_waitinglist_signup_confirmation(sender, entry, **kwargs):
    send_signup_confirmation(entry, user=kwargs.get("user"), auth=kwargs.get("auth"))


@receiver(waitinglist_entry_validate, dispatch_uid="sideburn_lottery_validate_duplicate_voucher")
def validate_waitinglist_duplicate_voucher(sender, entry, **kwargs):
    validate_no_active_voucher_duplicate(entry)


@receiver(waiting_list_send_voucher, dispatch_uid="sideburn_lottery_ignore_quota")
def allow_waitinglist_ignore_quota(sender, entry, **kwargs):
    return {"ignore_quota": True}
