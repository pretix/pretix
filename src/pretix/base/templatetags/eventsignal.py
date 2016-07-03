import importlib

from django import template

from pretix.base.models import Event

register = template.Library()


@register.simple_tag
def eventsignal(event: Event, signame: str, **kwargs):
    """
    Send a signal and return the concatenated return values of all responses.

    Usage::

        {% eventsignal event "path.to.signal" argument="value" ... %}
    """
    sigstr = signame.rsplit('.', 1)
    sigmod = importlib.import_module(sigstr[0])
    signal = getattr(sigmod, sigstr[1])
    _html = []
    for receiver, response in signal.send(event, **kwargs):
        _html.append(response)
    return "".join(_html)
