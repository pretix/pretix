from django.dispatch import receiver

from pretix.base.signals import register_ticket_outputs


@receiver(register_ticket_outputs, dispatch_uid="output_dummy")
def register_ticket_outputs(sender, **kwargs):
    from .ticketoutput import DummyTicketOutput
    return DummyTicketOutput
