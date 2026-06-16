from django.dispatch import receiver

from pretix.base.email import SimpleFunctionalMailTextPlaceholder
from pretix.base.signals import register_mail_placeholders

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
