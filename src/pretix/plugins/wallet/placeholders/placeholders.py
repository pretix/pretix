from django.contrib.staticfiles import finders
from django.core.files import File
from django.dispatch import receiver
from django.templatetags.static import static

from pretix.base.models.event import Event
from pretix.base.templatetags.money import money_filter
from pretix.multidomain.urlreverse import eventreverse_absolute
from pretix.plugins.wallet.i18n import (
    FormattingLocalizableString, GettextLocalizableString, LocalizableDatetime,
)

from ..signals import register_wallet_placeholders
from .base import (
    BaseWalletPlaceholder, FunctionalContextTransformation,
    FunctionalWalletImagePlaceholder, FunctionalWalletTextPlaceholder,
    WalletPlaceholderRenderer,
)


def get_wallet_placeholder_renderer(**kwargs):
    return WalletPlaceholderRenderer(
        **kwargs,
        transformations=[
            # TODO: make this extendable via signal?
            FunctionalContextTransformation(
                "item", {"order_position"}, lambda order_position: order_position.item
            ),
            FunctionalContextTransformation(
                "order", {"order_position"}, lambda order_position: order_position.order
            ),
            FunctionalContextTransformation(
                "event", {"order"}, lambda order: order.event
            ),
            FunctionalContextTransformation(
                "organizer", {"event"}, lambda event: event.organizer
            ),
            FunctionalContextTransformation(
                "subevent_or_event",
                {"order_position"},
                lambda order_position: order_position.subevent
                or order_position.order.event,
            ),
            FunctionalContextTransformation(
                "seat",
                {"order_position"},
                lambda order_position: (
                    order_position.seat if order_position.seat_id else None
                ),
            ),
        ],
    )


def get_wallet_placeholders(event) -> dict[str, dict[str, BaseWalletPlaceholder]]:
    placeholders = {"text": {}, "image": {}}
    for r, ps in register_wallet_placeholders.send(sender=event):
        for placeholder in ps:
            placeholders[placeholder.content_type][placeholder.identifier] = placeholder
    return placeholders


def get_static_file(name) -> File | None:
    path: str | None = finders.find(name)  # type: ignore
    if not path:
        return
    return File(open(path, "rb"))


def admission(subevent_or_event):
    return (
        LocalizableDatetime(
            subevent_or_event.date_admission.astimezone(subevent_or_event.timezone),
            "SHORT_DATETIME_FORMAT",
        )
        if subevent_or_event.date_admission
        else None
    )


def date_from(subevent_or_event):
    return LocalizableDatetime(
        subevent_or_event.date_from.astimezone(subevent_or_event.timezone),
        "SHORT_DATETIME_FORMAT",
    )


def admission_or_date_from(subevent_or_event):
    return admission(subevent_or_event) or date_from(subevent_or_event)


def website(order_position, order):
    if order_position.subevent:
        return eventreverse_absolute(
            order.event,
            "presale:event.index",
            {"subevent": order_position.subevent.pk},
        )
    else:
        return eventreverse_absolute(order.event, "presale:event.index")


@receiver(
    register_wallet_placeholders,
    dispatch_uid="plugin_wallet_register_wallet_placeholders",
)
def base_text_placeholders(sender: Event, **kwargs):
    return [
        FunctionalWalletTextPlaceholder(
            "event",
            GettextLocalizableString.gettext("Event"),
            {"event"},
            lambda event: event.name,
        ),
        FunctionalWalletTextPlaceholder(
            "event_slug",
            GettextLocalizableString.gettext("Event Slug"),
            {"event"},
            lambda event: event.slug,
        ),
        FunctionalWalletTextPlaceholder(
            "admission",
            GettextLocalizableString.gettext("Admission"),
            {"subevent_or_event"},
            admission,
            date_from,
        ),
        FunctionalWalletTextPlaceholder(
            "date_from",
            GettextLocalizableString.gettext("Begin"),
            {"subevent_or_event"},
            date_from,
        ),
        FunctionalWalletTextPlaceholder(
            "admission_or_date_from",
            GettextLocalizableString.gettext("Admission or Date From"),
            {"subevent_or_event"},
            admission_or_date_from,
        ),
        FunctionalWalletTextPlaceholder(
            "order",
            GettextLocalizableString.gettext("Order Code"),
            {"order"},
            lambda order: order.code,
        ),
        FunctionalWalletTextPlaceholder(
            "total",
            GettextLocalizableString.gettext("Order Total"),
            {"event", "order"},
            lambda event, order: money_filter(order.total, event.currency),
        ),
        FunctionalWalletTextPlaceholder(
            "order_email",
            GettextLocalizableString.gettext("Order Email"),
            {"order"},
            lambda order: order.email,
        ),
        FunctionalWalletTextPlaceholder(
            "price",
            GettextLocalizableString.gettext("Item Price"),
            {"event", "order_position"},
            lambda event, order_position: money_filter(
                order_position.price, event.currency
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "secret",
            GettextLocalizableString.gettext("Order Secret (QR-Code-Content)"),
            {"order_position"},
            lambda order_position: order_position.secret,
        ),
        FunctionalWalletTextPlaceholder(
            "item",
            GettextLocalizableString.gettext("Product"),
            {"item"},
            lambda item: item.name,
        ),
        FunctionalWalletTextPlaceholder(
            "item_description",
            GettextLocalizableString.gettext("Product description"),
            {"item"},
            lambda item: item.description,
        ),
        FunctionalWalletTextPlaceholder(
            "item_with_variation",
            GettextLocalizableString.gettext("Product and variation"),
            {"order_position"},
            lambda order_position: (
                FormattingLocalizableString(
                    "{name} - {variation}",
                    name=order_position.item.name,
                    variation=order_position.variation.name,
                )
                if order_position.variation
                else order_position.item.name
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "seat",
            GettextLocalizableString.gettext("Seat: Full name"),
            {"seat"},
            lambda seat: (
                FormattingLocalizableString("{seat}", seat=seat) if seat else None
            ),
            GettextLocalizableString.gettext("Ground floor, Row 3, Seat 4")
        ),
        FunctionalWalletTextPlaceholder(
            "seat_zone",
            GettextLocalizableString.gettext("Seat: Zone"),
            {"seat"},
            lambda seat: seat.zone_name,
            GettextLocalizableString.gettext("Ground floor"),
        ),
        FunctionalWalletTextPlaceholder(
            "seat_row",
            GettextLocalizableString.gettext("Seat: Row"),
            {"seat"},
            lambda seat: seat.row_label or seat.row_name,
            "C",
        ),
        FunctionalWalletTextPlaceholder(
            "seat_number",
            GettextLocalizableString.gettext("Seat: Seat Number"),
            {"seat"},
            lambda seat: seat.seat_label or seat.seat_number,
            "5",
        ),
        FunctionalWalletTextPlaceholder(
            "attendee_name",
            GettextLocalizableString.gettext("Attendee name"),
            {"order_position"},
            lambda order_position: order_position.attendee_name,
        ),
        FunctionalWalletTextPlaceholder(
            "program_start",
            GettextLocalizableString.gettext("Programm times: Start"),
            {"item", "subevent_or_event"},
            lambda item, subevent_or_event: (
                LocalizableDatetime(
                    min(pt.start for pt in item.program_times.all()).astimezone(
                        subevent_or_event.timezone
                    ),
                    "SHORT_DATETIME_FORMAT",
                )
                if item.program_times.all()
                else None
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "program_end",
            GettextLocalizableString.gettext("Programm times: End"),
            {"item", "subevent_or_event"},
            lambda item, subevent_or_event: (
                LocalizableDatetime(
                    max(pt.end for pt in item.program_times.all()).astimezone(
                        subevent_or_event.timezone
                    ),
                    "SHORT_DATETIME_FORMAT",
                )
                if item.program_times.all()
                else None
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "organizer",
            GettextLocalizableString.gettext("Organizer"),
            {"organizer"},
            lambda organizer: organizer.name,
        ),
        FunctionalWalletTextPlaceholder(
            "organizer_contact",
            GettextLocalizableString.gettext("Organizer Contact"),
            {"event"},
            lambda event: event.settings.contact_mail,
            "contact@example.com",
        ),
        FunctionalWalletTextPlaceholder(
            "order_code",
            GettextLocalizableString.gettext("Order Code"),
            {"order"},
            lambda order: order.code,
        ),
        FunctionalWalletTextPlaceholder(
            "purchase_date",
            GettextLocalizableString.gettext("Purchase Date"),
            {"order", "subevent_or_event"},
            lambda order, subevent_or_event: LocalizableDatetime(
                order.datetime.astimezone(subevent_or_event.timezone),
                "SHORT_DATETIME_FORMAT",
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "website",
            GettextLocalizableString.gettext("Website"),
            {"order_position", "order"},
            website,
        ),
        # IMAGES
        FunctionalWalletImagePlaceholder(
            "poweredby_logo",
            GettextLocalizableString.gettext("Logo"),
            set(),
            lambda: get_static_file("pretixplugins/wallet/logo.png"),
            static("pretixplugins/wallet/logo.png"),
        ),
        FunctionalWalletImagePlaceholder(
            "poweredby_icon",
            GettextLocalizableString.gettext("Icon"),
            set(),
            lambda: get_static_file("pretixplugins/wallet/icon.png"),
            static("pretixplugins/wallet/icon.png"),
        ),
        # TODO: Image upload
    ]
