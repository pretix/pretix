from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from pretix.base.models import (
    Event, Item, ItemCategory, ItemVariation, Quota, SubEvent,
)
from pretix.base.models.tax import TaxedPrice
from pretix.base.storelogic.products import (
    get_items_for_product_list, item_group_by_category,
)
from pretix.base.templatetags.rich_text import rich_text
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix.storefrontapi.permission import StorefrontEventPermission
from pretix.storefrontapi.serializers import I18nFlattenedModelSerializer


def opt_str(o):
    if o is None:
        return None
    return str(o)


class RichTextField(serializers.Field):
    def to_representation(self, value):
        return rich_text(value)


class DynamicAttrField(serializers.Field):
    def __init__(self, *args, **kwargs):
        self.attr = kwargs.pop("attr")
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        return getattr(value, self.attr)


class EventURLField(serializers.Field):
    def to_representation(self, ev):
        if isinstance(ev, SubEvent):
            return build_absolute_uri(
                ev.event, "presale:event.index", kwargs={"subevent": ev.pk}
            )
        return build_absolute_uri(ev, "presale:event.index")


class EventSettingsField(serializers.Field):
    def to_representation(self, ev):
        event = ev.event if isinstance(ev, SubEvent) else ev
        return {
            "display_net_prices": event.settings.display_net_prices,
            "show_variations_expanded": event.settings.show_variations_expanded,
            "show_times": event.settings.show_times,
            "show_dates_on_frontpage": event.settings.show_dates_on_frontpage,
            "voucher_explanation_text": str(
                rich_text(event.settings.voucher_explanation_text, safelinks=False)
            ),
            "frontpage_text": str(
                rich_text(
                    (
                        ev.frontpage_text
                        if isinstance(ev, SubEvent)
                        else event.settings.frontpage_text
                    ),
                    safelinks=False,
                )
            ),
        }


class CategorySerializer(I18nFlattenedModelSerializer):
    description = RichTextField()

    class Meta:
        model = ItemCategory
        fields = [
            "id",
            "name",
            "description",
        ]


class PricingField(serializers.Field):
    def to_representation(self, item_or_var):
        if isinstance(item_or_var, Item) and item_or_var.has_variations:
            return None

        item = item_or_var if isinstance(item_or_var, Item) else item_or_var.item
        suggested_price = item_or_var.suggested_price
        display_price = item_or_var.display_price

        if self.context.get("price_included"):
            display_price = TaxedPrice(
                gross=Decimal("0.00"),
                net=Decimal("0.00"),
                tax=Decimal("0.00"),
                rate=Decimal("0.00"),
                name="",
                code=None,
            )

        if hasattr(item, "initial_price"):
            # Pre-select current price for add-ons
            suggested_price = item_or_var.initial_price

        return {
            "display_price": {
                "net": opt_str(display_price.net),
                "gross": opt_str(display_price.gross),
                "tax_rate": opt_str(
                    display_price.rate if not item.includes_mixed_tax_rate else None
                ),
                "tax_name": opt_str(
                    display_price.name if not item.includes_mixed_tax_rate else None
                ),
            },
            "original_price": (
                {
                    "net": opt_str(item_or_var.original_price.net),
                    "gross": opt_str(item_or_var.original_price.gross),
                    "tax_rate": opt_str(
                        item_or_var.original_price.rate
                        if not item.includes_mixed_tax_rate
                        else None
                    ),
                    "tax_name": opt_str(
                        item_or_var.original_price.name
                        if not item.includes_mixed_tax_rate
                        else None
                    ),
                }
                if item_or_var.original_price
                else None
            ),
            "free_price": item.free_price,
            "suggested_price": {
                "net": opt_str(suggested_price.net),
                "gross": opt_str(suggested_price.gross),
                "tax_rate": opt_str(
                    suggested_price.rate if not item.includes_mixed_tax_rate else None
                ),
                "tax_name": opt_str(
                    suggested_price.name if not item.includes_mixed_tax_rate else None
                ),
            },
            "mandatory_priced_addons": getattr(item, "mandatory_priced_addons", False),
            "includes_mixed_tax_rate": item.includes_mixed_tax_rate,
        }


class AvailabilityField(serializers.Field):
    def to_representation(self, item_or_var):
        if isinstance(item_or_var, Item) and item_or_var.has_variations:
            return None

        item = item_or_var if isinstance(item_or_var, Item) else item_or_var.item

        if (
            item_or_var.current_unavailability_reason == "require_voucher"
            or item.current_unavailability_reason == "require_voucher"
        ):
            return {
                "available": False,
                "code": "require_voucher",
                "message": _("Enter a voucher code below to buy this product."),
                "waiting_list": False,
                "max_selection": 0,
                "quota_left": None,
            }
        elif (
            item_or_var.current_unavailability_reason == "available_from"
            or item.current_unavailability_reason == "available_from"
        ):
            return {
                "available": False,
                "code": "available_from",
                "message": _("Not available yet."),
                "waiting_list": False,
                "max_selection": 0,
                "quota_left": None,
            }
        elif (
            item_or_var.current_unavailability_reason == "available_until"
            or item.current_unavailability_reason == "available_until"
        ):
            return {
                "available": False,
                "code": "available_until",
                "message": _("Not available any more."),
                "waiting_list": False,
                "max_selection": 0,
                "quota_left": None,
            }
        elif item_or_var.cached_availability[0] <= Quota.AVAILABILITY_ORDERED:
            return {
                "available": False,
                "code": "sold_out",
                "message": _("SOLD OUT"),
                "waiting_list": self.context["allow_waitinglist"]
                and item.allow_waitinglist,
                "max_selection": 0,
                "quota_left": 0,
            }
        elif item_or_var.cached_availability[0] < Quota.AVAILABILITY_OK:
            return {
                "available": False,
                "code": "reserved",
                "message": _(
                    "All remaining products are reserved but might become available again."
                ),
                "waiting_list": self.context["allow_waitinglist"]
                and item.allow_waitinglist,
                "max_selection": 0,
                "quota_left": 0,
            }
        else:
            return {
                "available": True,
                "code": "ok",
                "message": None,
                "waiting_list": False,
                "max_selection": self.context.get("max_count", item_or_var.order_max),
                "quota_left": (
                    item_or_var.cached_availability[1]
                    if item.show_quota_left
                    and item_or_var.cached_availability[1] is not None
                    else None
                ),
            }


class VariationSerializer(I18nFlattenedModelSerializer):
    description = RichTextField()
    pricing = PricingField(source="*")
    availability = AvailabilityField(source="*")

    class Meta:
        model = ItemVariation
        fields = [
            "id",
            "value",
            "description",
            "pricing",
            "availability",
        ]

    def to_representation(self, instance):
        r = super().to_representation(instance)
        if hasattr(instance, "initial"):
            # Used for addons
            r["initial_count"] = instance.initial
        return r


class ItemSerializer(I18nFlattenedModelSerializer):
    description = RichTextField()
    available_variations = VariationSerializer(many=True, read_only=True)
    pricing = PricingField(source="*")
    availability = AvailabilityField(source="*")
    has_variations = serializers.BooleanField(read_only=True)

    class Meta:
        model = Item
        fields = [
            "id",
            "name",
            "has_variations",
            "description",
            "picture",
            "min_per_order",
            "available_variations",
            "pricing",
            "availability",
        ]

    def to_representation(self, instance):
        r = super().to_representation(instance)
        if hasattr(instance, "initial"):
            # Used for addons
            r["initial_count"] = instance.initial
        return r


class ProductGroupField(serializers.Field):
    def to_representation(self, ev):
        event = ev.event if isinstance(ev, SubEvent) else ev

        items, display_add_to_cart = get_items_for_product_list(
            event,
            subevent=ev if isinstance(ev, SubEvent) else None,
            require_seat=False,
            channel=self.context["sales_channel"],
            voucher=None,  # TODO
            memberships=(
                self.context["customer"].usable_memberships(
                    for_event=ev, testmode=event.testmode
                )
                if self.context.get("customer")
                else None
            ),
        )
        return [
            {
                "category": (
                    CategorySerializer(cat, context=self.context).data if cat else None
                ),
                "items": ItemSerializer(items, many=True, context=self.context).data,
            }
            for cat, items in item_group_by_category(items)
        ]


class BaseEventDetailSerializer(I18nFlattenedModelSerializer):
    public_url = EventURLField(source="*", read_only=True)
    settings = EventSettingsField(source="*", read_only=True)

    class Meta:
        model = Event
        fields = [
            "name",
            "has_subevents",
            "public_url",
            "currency",
            "settings",
        ]

    def to_representation(self, ev):
        r = super().to_representation(ev)
        event = ev.event if isinstance(ev, SubEvent) else ev

        if not event.settings.presale_start_show_date or event.presale_is_running:
            r["effective_presale_start"] = None
        if not event.settings.show_date_to:
            r["date_to"] = None

        return r


class SubEventDetailSerializer(BaseEventDetailSerializer):
    testmode = serializers.BooleanField(source="event.testmode")
    has_subevents = serializers.BooleanField(source="event.has_subevents")
    product_list = ProductGroupField(source="*")

    # todo: vouchers_exist
    # todo: date range
    # todo: seating, seating waiting list

    class Meta:
        model = SubEvent
        fields = [
            "name",
            "testmode",
            "has_subevents",
            "public_url",
            "currency",
            "settings",
            "location",
            "date_from",
            "date_to",
            "date_admission",
            "presale_is_running",
            "effective_presale_start",
            "product_list",
        ]


class EventDetailSerializer(BaseEventDetailSerializer):
    # todo: vouchers_exist
    # todo: date range
    # todo: seating, seating waiting list
    product_list = ProductGroupField(source="*")

    class Meta:
        model = Event
        fields = [
            "name",
            "testmode",
            "has_subevents",
            "public_url",
            "currency",
            "settings",
            "location",
            "date_from",
            "date_to",
            "date_admission",
            "presale_is_running",
            "effective_presale_start",
            "product_list",
        ]


class EventViewSet(viewsets.ViewSet):
    queryset = Event.objects.none()
    lookup_url_kwarg = "event"
    lookup_field = "slug"
    permission_classes = [
        StorefrontEventPermission,
    ]

    def retrieve(self, request, *args, **kwargs):
        event = request.event  # Lookup is already done
        # todo: prefetch related items

        ctx = {
            "sales_channel": request.sales_channel,
            "customer": None,
            "event": event,
            "allow_waitinglist": True,
        }
        if event.has_subevents:
            if "subevent" in request.GET:
                ctx["event"] = request.event
                subevent = get_object_or_404(
                    request.event.subevents, pk=request.GET.get("subevent"), active=True
                )
                serializer = SubEventDetailSerializer(subevent, context=ctx)
            else:
                serializer = BaseEventDetailSerializer(event, context=ctx)
        else:
            serializer = EventDetailSerializer(event, context=ctx)
        return Response(serializer.data)
