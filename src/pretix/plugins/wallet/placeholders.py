from collections.abc import Callable
from functools import cached_property
from typing import Any

from django.contrib.staticfiles import finders
from django.core.files import File
from django.dispatch import receiver
from django.templatetags.static import static
from i18nfield.strings import LazyI18nString

from pretix.base.models.orders import OrderPosition
from pretix.base.templatetags.money import money_filter
from django.utils.formats import date_format

from pretix.multidomain.urlreverse import eventreverse_absolute

from .signals import register_wallet_placeholders


class BaseWalletPlaceholder:
    """
    This is the base class for all wallet placeholders.
    """

    @property
    def required_context(self) -> set[str]:
        """
        A a set of all attribute names that need to be contained in the base context so that this placeholder is available.
        """
        return set()

    @property
    def identifier(self) -> str:
        """The unique identifier of this placeholder"""
        raise NotImplementedError()

    @property
    def content_type(self) -> str:
        """The content type this placeholder generates (text / image)"""
        raise NotImplementedError()

    @property
    def label(self) -> LazyI18nString:
        """The human readable name of this placeholder"""
        raise NotImplementedError()

    @property
    def control_label(self) -> LazyI18nString:
        """
        The human readable name of this placeholder shown in the backend.

        Defaults to `label`
        """
        return self.label

    def render(self, **context):
        raise NotImplementedError()

    def render_sample(self, **context):
        raise NotImplementedError()


class BaseWalletTextPlaceholder(BaseWalletPlaceholder):
    @property
    def content_type(self) -> str:
        return "text"

    def render(self, **context) -> LazyI18nString | str | None:
        """
        This method is called to generate the text that is being shown on the pass.
        You will be passed the keyword arguments specified in ``required_context``.
        You are expected to return a plain-text string.
        """
        raise NotImplementedError()

    def render_sample(self, **context) -> LazyI18nString | str:
        """
        This method is called to generate a text to be used in previews.

        You will be passed sample instances of the arguments specified in ``required_context``.
        If those instances contain all data needed, you do not need to implement this.
        """
        sample = self.render(**context)
        if sample is None:
            raise RuntimeError("`render` returned None when rendering a sample")
        return sample


class BaseWalletImagePlaceholder(BaseWalletPlaceholder):
    @property
    def content_type(self) -> str:
        return "image"

    def render(self, **context) -> File | None:
        """
        This method is called to generate the image that is being shown on the pass.
        You will be passed the keyword arguments specified in ``required_context``.
        You are expected to return a `File` object.
        """
        raise NotImplementedError()

    def render_sample(self, **context) -> str | None:
        """
        This method is called to generate a text to be used in previews.

        You will be passed sample instances of the arguments specified in ``required_context``.
        You are expected to return a URL to a sample image or `None` if no sample can be shown.
        """
        return None


class FunctionalWalletTextPlaceholder(BaseWalletTextPlaceholder):
    def __init__(
        self,
        identifier: str,
        label: LazyI18nString,
        args: set[str],
        func: Callable[..., LazyI18nString | str | None],
        sample: (
            None | LazyI18nString | str | Callable[..., str | LazyI18nString]
        ) = None,
    ):
        self._identifier = identifier
        self._label = label
        self._args = args
        self.render = func
        self._sample = sample

    @property
    def identifier(self):
        return self._identifier

    @property
    def label(self):
        return self._label

    @property
    def required_context(self) -> set[str]:
        return self._args

    def render_sample(self, **context) -> LazyI18nString | str:
        if isinstance(self._sample, Callable):
            return self._sample(**context)
        elif self._sample:
            return self._sample
        else:
            return super().render_sample(**context)


class FunctionalWalletImagePlaceholder(BaseWalletImagePlaceholder):
    def __init__(
        self,
        identifier: str,
        label: LazyI18nString,
        args: set[str],
        func: Callable[..., File | None],
        sample: None | str | Callable[..., str] = None,
    ):
        self._identifier = identifier
        self._label = label
        self._args = args
        self.render = func
        self._sample = sample

    @property
    def required_context(self) -> set[str]:
        return self._args

    @property
    def identifier(self):
        return self._identifier

    @property
    def label(self):
        return self._label

    def render_sample(self, **context) -> str | None:
        if isinstance(self._sample, Callable):
            return self._sample(**context)
        return self._sample


class MissingContextException(Exception):
    pass


class PlaceholderContextTransformation:
    @property
    def required_context(self) -> set[str]:
        """
        A a set of all attribute names that need to be contained in the base context for this transformation to function.
        """
        return set()

    @property
    def generated_context_name(self) -> str:
        """The name of the context arg this transformation produces"""
        raise NotImplementedError()

    def transform(self, context):
        raise NotImplementedError("`transform` not implemented")


class FunctionalContextTransformation(PlaceholderContextTransformation):
    def __init__(self, context_name: str, context_args: set[str], func: Callable):
        self.context_args = context_args
        self.context_name = context_name
        self.transform = func

    @property
    def required_context(self) -> set[str]:
        return self.context_args

    @property
    def generated_context_name(self) -> str:
        return self.context_name


def get_available_context(
    initial_context: set[str], transformations: list[PlaceholderContextTransformation]
):
    used_trans = set()
    available_context = set(initial_context)
    changed = True
    while changed:
        changed = False
        for trans in transformations:
            if trans in used_trans:
                continue

            if trans.required_context <= available_context:
                used_trans.add(trans)
                if trans.generated_context_name not in available_context:
                    available_context.add(trans.generated_context_name)
                    changed = True

    return available_context


def get_transformed_context(
    context_args: dict[str, Any],
    transformations: list[PlaceholderContextTransformation],
):
    used_trans = set()
    transformed_context_args = dict(context_args)
    changed = True
    while changed:
        changed = False
        for trans in transformations:
            if trans in used_trans:
                continue

            if trans.required_context <= transformed_context_args.keys():
                used_trans.add(trans)
                if trans.generated_context_name not in transformed_context_args.keys():
                    transformation_context = {
                        k: v
                        for k, v in transformed_context_args.items()
                        if k in trans.required_context
                    }
                    transformed_context_args[trans.generated_context_name] = (
                        trans.transform(**transformation_context)
                    )
                    changed = True

    return transformed_context_args


class WalletPlaceholderRenderer:
    def __init__(
        self,
        *,
        transformations: list[PlaceholderContextTransformation] | None = None,
        **kwargs,
    ):
        self.context = kwargs
        self.cache = {}
        self.transformations = list(transformations) if transformations else []

    @cached_property
    def _get_transformed_context(self):
        return get_transformed_context(self.context, self.transformations)

    def _get_placeholder_context(self, placeholder: BaseWalletPlaceholder):
        context = self._get_transformed_context
        missing_context = placeholder.required_context - context.keys()
        if missing_context:
            raise MissingContextException(
                f"Missing context args for '{placeholder.identifier}': {', '.join(missing_context)}"
            )

        return {k: v for k, v in context.items() if k in placeholder.required_context}

    def is_available(self, placeholder: BaseWalletPlaceholder, context_args: set[str]):
        available_context = get_available_context(context_args, self.transformations)
        missing_context = placeholder.required_context - available_context
        return not missing_context

    def render_placeholder(self, placeholder: BaseWalletPlaceholder):
        if placeholder.identifier in self.cache:
            return self.cache[placeholder.identifier]

        value = self.cache[placeholder.identifier] = placeholder.render(
            **self._get_placeholder_context(placeholder)
        )
        return value

    def render_sample(self, placeholder: BaseWalletPlaceholder):
        return placeholder.render_sample(**self._get_placeholder_context(placeholder))


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
                    order_position.seat
                    if order_position.seat_id
                    else (
                        order_position.addon_to.seat
                        if order_position.addon_to_id
                        else None
                    )
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
        subevent_or_event.date_admission.astimezone(subevent_or_event.timezone)
        if subevent_or_event.date_admission
        else None
    )


def date_from(subevent_or_event):
    return subevent_or_event.get_date_from_display(
        subevent_or_event.timezone, short=True
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
def base_text_placeholders(sender, **kwargs):
    return [
        FunctionalWalletTextPlaceholder(
            "event",
            LazyI18nString.from_gettext("Event"),
            {"event"},
            lambda event: event.name,
        ),
        FunctionalWalletTextPlaceholder(
            "event_slug",
            LazyI18nString.from_gettext("Event Slug"),
            {"event"},
            lambda event: event.slug,
        ),
        FunctionalWalletTextPlaceholder(
            "admission",
            LazyI18nString.from_gettext("Admission"),
            {"subevent_or_event"},
            admission,
            lambda subevent_or_event: subevent_or_event.get_date_from_display(
                subevent_or_event.timezone, short=True
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "date_from",
            LazyI18nString.from_gettext("Begin"),
            {"subevent_or_event"},
            date_from,
        ),
        FunctionalWalletTextPlaceholder(
            "admission_or_date_from",
            LazyI18nString.from_gettext("Admission or Date From"),
            {"subevent_or_event"},
            admission_or_date_from,
        ),
        FunctionalWalletTextPlaceholder(
            "order",
            LazyI18nString.from_gettext("Order Code"),
            {"order"},
            lambda order: order.code,
        ),
        FunctionalWalletTextPlaceholder(
            "total",
            LazyI18nString.from_gettext("Order Total"),
            {"event", "order"},
            lambda event, order: money_filter(order.total, event.currency),
        ),
        FunctionalWalletTextPlaceholder(
            "order_email",
            LazyI18nString.from_gettext("Order Email"),
            {"order"},
            lambda order: order.email,
        ),
        FunctionalWalletTextPlaceholder(
            "price",
            LazyI18nString.from_gettext("Item Price"),
            {"event", "order_position"},
            lambda event, order_position: money_filter(
                order_position.price, event.currency
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "secret",
            LazyI18nString.from_gettext("Order Secret (QR-Code-Content)"),
            {"order_position"},
            lambda order_position: order_position.secret,
        ),
        FunctionalWalletTextPlaceholder(
            "item",
            LazyI18nString.from_gettext("Product"),
            {"item"},
            lambda item: item.name,
        ),
        FunctionalWalletTextPlaceholder(
            "item_description",
            LazyI18nString.from_gettext("Product description"),
            {"item"},
            lambda item: item.description,
        ),
        FunctionalWalletTextPlaceholder(
            "item_with_variation",
            LazyI18nString.from_gettext("Product and variation"),
            {"order_position"},
            lambda order_position: (
                f"{order_position.item.name} - {order_position.variation}"
                if order_position.variation
                else order_position.item.name
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "seat",
            LazyI18nString.from_gettext("Seat: Full name"),
            {"event", "seat"},
            lambda event, seat: (
                seat
                if seat
                else (
                    LazyI18nString.from_gettext("General admission")
                    if event.seating_plan_id is not None
                    else ""
                )
            ),
            LazyI18nString.from_gettext("Ground floor, Row 3, Seat 4"),
        ),
        FunctionalWalletTextPlaceholder(
            "seat_zone",
            LazyI18nString.from_gettext("Seat: zone"),
            {"event", "seat"},
            lambda event, seat: (
                seat.zone_name
                if seat
                else (
                    LazyI18nString.from_gettext("General admission")
                    if event.seating_plan_id is not None
                    else ""
                )
            ),
            LazyI18nString.from_gettext("Ground floor"),
        ),
        FunctionalWalletTextPlaceholder(
            "attendee_name",
            LazyI18nString.from_gettext("Attendee name"),
            {"order_position"},
            lambda order_position: order_position.attendee_name,
        ),
        FunctionalWalletTextPlaceholder(
            "program_start",
            LazyI18nString.from_gettext("Programm times: Start"),
            {"item", "subevent_or_event"},
            lambda item, subevent_or_event: (
                date_format(
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
            LazyI18nString.from_gettext("Programm times: End"),
            {"item", "subevent_or_event"},
            lambda item, subevent_or_event: (
                date_format(
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
            LazyI18nString.from_gettext("Organizer"),
            {"organizer"},
            lambda organizer: organizer.name,
        ),
        FunctionalWalletTextPlaceholder(
            "organizer_contact",
            LazyI18nString.from_gettext("Organizer Contact"),
            {"event"},
            lambda event: event.settings.contact_mail,
            "contact@example.com",
        ),
        FunctionalWalletTextPlaceholder(
            "order_code",
            LazyI18nString.from_gettext("Order Code"),
            {"order"},
            lambda order: order.code,
        ),
        FunctionalWalletTextPlaceholder(
            "purchase_date",
            LazyI18nString.from_gettext("Purchase Date"),
            {"order", "subevent_or_event"},
            lambda order, subevent_or_event: date_format(
                order.datetime.astimezone(subevent_or_event.timezone),
                "SHORT_DATETIME_FORMAT",
            ),
        ),
        FunctionalWalletTextPlaceholder(
            "website",
            LazyI18nString.from_gettext("Website"),
            {"order_position", "order"},
            website,
        ),
        # IMAGES
        FunctionalWalletImagePlaceholder(
            "poweredby",
            LazyI18nString.from_gettext("Logo"),
            set(),
            # TODO: replace with paths not from another plugin
            lambda: get_static_file("pretix_passbook/logo.png"),
            static("pretix_passbook/logo.png"),
        ),
        FunctionalWalletImagePlaceholder(
            "poweredby_icon",
            LazyI18nString.from_gettext("Icon"),
            set(),
            lambda: get_static_file("pretix_passbook/icon.png"),
            static("pretix_passbook/icon.png"),
        ),
        FunctionalWalletImagePlaceholder(
            "example_no_preview",
            LazyI18nString.from_gettext("Image with no preview"),
            set(),
            lambda: get_static_file("pretix_passbook/icon.png"),
        ),
        # TODO: Image upload
    ]
