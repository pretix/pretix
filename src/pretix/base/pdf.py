import copy
from collections import OrderedDict

from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _
from pytz import timezone

from pretix.base.signals import layout_text_variables
from pretix.base.templatetags.money import money_filter

DEFAULT_VARIABLES = OrderedDict((
    ("secret", {
        "label": _("Ticket code (barcode content)"),
        "editor_sample": "tdmruoekvkpbv1o2mv8xccvqcikvr58u",
        "evaluate": lambda orderposition, order, event: orderposition.secret
    }),
    ("order", {
        "label": _("Order code"),
        "editor_sample": "A1B2C",
        "evaluate": lambda orderposition, order, event: orderposition.order.code
    }),
    ("item", {
        "label": _("Product name"),
        "editor_sample": _("Sample product"),
        "evaluate": lambda orderposition, order, event: str(orderposition.item)
    }),
    ("variation", {
        "label": _("Variation name"),
        "editor_sample": _("Sample variation"),
        "evaluate": lambda op, order, event: str(op.variation) if op.variation else ''
    }),
    ("item_description", {
        "label": _("Product description"),
        "editor_sample": _("Sample product description"),
        "evaluate": lambda orderposition, order, event: str(orderposition.item.description)
    }),
    ("itemvar", {
        "label": _("Product name and variation"),
        "editor_sample": _("Sample product – sample variation"),
        "evaluate": lambda orderposition, order, event: (
            '{} - {}'.format(orderposition.item, orderposition.variation)
            if orderposition.variation else str(orderposition.item)
        )
    }),
    ("item_category", {
        "label": _("Product category"),
        "editor_sample": _("Ticket category"),
        "evaluate": lambda orderposition, order, event: (
            str(orderposition.item.category.name) if orderposition.item.category else ""
        )
    }),
    ("price", {
        "label": _("Price"),
        "editor_sample": _("123.45 EUR"),
        "evaluate": lambda op, order, event: money_filter(op.price, event.currency)
    }),
    ("attendee_name", {
        "label": _("Attendee name"),
        "editor_sample": _("John Doe"),
        "evaluate": lambda op, order, ev: op.attendee_name or (op.addon_to.attendee_name if op.addon_to else '')
    }),
    ("event_name", {
        "label": _("Event name"),
        "editor_sample": _("Sample event name"),
        "evaluate": lambda op, order, ev: str(ev.name)
    }),
    ("event_date", {
        "label": _("Event date"),
        "editor_sample": _("May 31st, 2017"),
        "evaluate": lambda op, order, ev: ev.get_date_from_display(show_times=False)
    }),
    ("event_date_range", {
        "label": _("Event date range"),
        "editor_sample": _("May 31st – June 4th, 2017"),
        "evaluate": lambda op, order, ev: ev.get_date_range_display()
    }),
    ("event_begin", {
        "label": _("Event begin date and time"),
        "editor_sample": _("2017-05-31 20:00"),
        "evaluate": lambda op, order, ev: ev.get_date_from_display(show_times=True)
    }),
    ("event_begin_time", {
        "label": _("Event begin time"),
        "editor_sample": _("20:00"),
        "evaluate": lambda op, order, ev: ev.get_time_from_display()
    }),
    ("event_end", {
        "label": _("Event end date and time"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_to.astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATETIME_FORMAT"
        ) if ev.date_to else ""
    }),
    ("event_end_time", {
        "label": _("Event end time"),
        "editor_sample": _("19:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_to.astimezone(timezone(ev.settings.timezone)),
            "TIME_FORMAT"
        ) if ev.date_to else ""
    }),
    ("event_admission", {
        "label": _("Event admission date and time"),
        "editor_sample": _("2017-05-31 19:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_admission.astimezone(timezone(ev.settings.timezone)),
            "SHORT_DATETIME_FORMAT"
        ) if ev.date_admission else ""
    }),
    ("event_admission_time", {
        "label": _("Event admission time"),
        "editor_sample": _("19:00"),
        "evaluate": lambda op, order, ev: date_format(
            ev.date_admission.astimezone(timezone(ev.settings.timezone)),
            "TIME_FORMAT"
        ) if ev.date_admission else ""
    }),
    ("event_location", {
        "label": _("Event location"),
        "editor_sample": _("Random City"),
        "evaluate": lambda op, order, ev: str(ev.location).replace("\n", "<br/>\n")
    }),
    ("invoice_name", {
        "label": _("Invoice address: name"),
        "editor_sample": _("John Doe"),
        "evaluate": lambda op, order, ev: order.invoice_address.name if getattr(order, 'invoice_address') else ''
    }),
    ("invoice_company", {
        "label": _("Invoice address: company"),
        "editor_sample": _("Sample company"),
        "evaluate": lambda op, order, ev: order.invoice_address.company if getattr(order, 'invoice_address') else ''
    }),
    ("addons", {
        "label": _("List of Add-Ons"),
        "editor_sample": _("Addon 1\nAddon 2"),
        "evaluate": lambda op, order, ev: "<br/>".join([
            '{} - {}'.format(p.item, p.variation) if p.variation else str(p.item)
            for p in op.addons.select_related('item', 'variation')
        ])
    }),
    ("organizer", {
        "label": _("Organizer name"),
        "editor_sample": _("Event organizer company"),
        "evaluate": lambda op, order, ev: str(order.event.organizer.name)
    }),
    ("organizer_info_text", {
        "label": _("Organizer info text"),
        "editor_sample": _("Event organizer info text"),
        "evaluate": lambda op, order, ev: str(order.event.settings.organizer_info_text)
    }),
))


def get_variables(event):
    v = copy.copy(DEFAULT_VARIABLES)
    for recv, res in layout_text_variables.send(sender=event):
        v.update(res)
    return v
