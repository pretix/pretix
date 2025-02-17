import logging

from celery.result import AsyncResult
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils import translation
from django.utils.translation import gettext as _
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.reverse import reverse

from pretix.base.models import Item, ItemVariation, SubEvent, TaxRule
from pretix.base.models.orders import CartPosition, CheckoutSession, OrderFee
from pretix.base.services.cart import (
    add_items_to_cart, add_payment_to_cart_session, error_messages, get_fees,
    set_cart_addons,
)
from pretix.base.services.orders import perform_order
from pretix.base.storelogic.addons import get_addon_groups
from pretix.base.storelogic.fields import (
    get_checkout_fields, get_position_fields,
)
from pretix.base.storelogic.payment import current_selected_payments
from pretix.base.timemachine import time_machine_now
from pretix.presale.signals import (
    order_api_meta_from_request, order_meta_from_request,
)
from pretix.presale.views.cart import generate_cart_id
from pretix.storefrontapi.endpoints.event import (
    CategorySerializer, ItemSerializer,
)
from pretix.storefrontapi.permission import StorefrontEventPermission
from pretix.storefrontapi.serializers import I18nFlattenedModelSerializer
from pretix.storefrontapi.steps import get_steps

logger = logging.getLogger(__name__)


class CartAddLineSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    variation = serializers.IntegerField(allow_null=True, required=False)
    subevent = serializers.IntegerField(allow_null=True, required=False)
    count = serializers.IntegerField(default=1)
    seat = serializers.CharField(allow_null=True, required=False)
    price = serializers.DecimalField(
        allow_null=True, required=False, decimal_places=2, max_digits=13
    )
    voucher = serializers.CharField(allow_null=True, required=False)


class CartAddonLineSerializer(CartAddLineSerializer):
    voucher = None
    addon_to = serializers.PrimaryKeyRelatedField(
        queryset=CartPosition.objects.none(), required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["addon_to"].queryset = CartPosition.objects.filter(
            cart_id=self.context["cart_id"], addon_to__isnull=True
        )

    def to_internal_value(self, data):
        i = super().to_internal_value(data)
        i["addon_to"] = i["addon_to"].pk
        return i


class InlineItemSerializer(I18nFlattenedModelSerializer):

    class Meta:
        model = Item
        fields = [
            "id",
            "name",
        ]


class InlineItemVariationSerializer(I18nFlattenedModelSerializer):

    class Meta:
        model = ItemVariation
        fields = [
            "id",
            "value",
        ]


class InlineSubEventSerializer(I18nFlattenedModelSerializer):

    class Meta:
        model = SubEvent
        fields = [
            "id",
            "name",
            "date_from",
        ]


class CartFeeSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderFee
        fields = [
            "fee_type",
            "description",
            "value",
            "tax_rate",
            "tax_value",
            "internal_type",
        ]


class FieldSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    label = serializers.CharField(allow_null=True)
    required = serializers.BooleanField()
    type = serializers.CharField()
    validation_hints = serializers.DictField()


class MinimalCartPositionSerializer(serializers.ModelSerializer):
    # todo: prefetch related items
    item = InlineItemSerializer(read_only=True)
    variation = InlineItemVariationSerializer(read_only=True)
    subevent = InlineSubEventSerializer(read_only=True)

    class Meta:
        model = CartPosition
        fields = [
            "id",
            "addon_to",
            "item",
            "variation",
            "subevent",
            "price",
            "expires",
            # todo: attendee_name, attendee_email, voucher, addon_to, used_membership, seat, is_bundled, discount
            # todo: address, requested_valid_from
        ]


class CartPositionSerializer(MinimalCartPositionSerializer):
    def to_representation(self, instance):
        d = super().to_representation(instance)
        fields = get_position_fields(self.context["event"], instance)
        d["fields"] = FieldSerializer(
            fields, many=True, context={**self.context, "position": instance}
        ).data
        d["fields_data"] = {f.identifier: f.current_value(instance) for f in fields}
        return d


class CheckoutSessionSerializer(serializers.ModelSerializer):

    class Meta:
        model = CheckoutSession
        fields = [
            "cart_id",
            "sales_channel",
            "testmode",
        ]

    def to_representation(self, checkout):
        d = super().to_representation(checkout)

        cartpos = checkout.get_cart_positions(prefetch_questions=True)
        total = sum(p.price for p in cartpos)

        try:
            fees = get_fees(
                self.context["event"],
                self.context["request"],
                total,
                (
                    checkout.invoice_address
                    if hasattr(checkout, "invoice_address")
                    else None
                ),
                payments=[],  # todo
                positions=cartpos,
            )
        except TaxRule.SaleNotAllowed:
            # ignore for now, will fail on order creation
            fees = []

        total += sum([f.value for f in fees])
        d["cart_positions"] = CartPositionSerializer(
            sorted(cartpos, key=lambda c: c.sort_key), many=True, context=self.context
        ).data
        d["cart_fees"] = CartFeeSerializer(fees, many=True, context=self.context).data
        d["total"] = str(total)

        fields = get_checkout_fields(self.context["event"])
        d["fields"] = FieldSerializer(
            fields, many=True, context={**self.context, "checkout": checkout}
        ).data
        d["fields_data"] = {
            f.identifier: f.current_value(checkout.session_data) for f in fields
        }

        payments = current_selected_payments(
            self.context["event"],
            total,
            checkout.session_data,
            total_includes_payment_fees=False,
            fail=False,
        )
        d["payments"] = [
            {
                "identifier": p["pprov"].identifier,
                "label": str(p["pprov"].public_name),
                "payment_amount": str(p["payment_amount"]),
            }
            for p in payments
        ]

        d["steps"] = {}
        if cartpos:
            steps = get_steps(
                self.context["event"],
                cartpos,
                getattr(checkout, "invoice_address", None),
                checkout.session_data,
                total,
            )
            for step in steps:
                applicable = step.is_applicable()
                valid = not applicable or step.is_valid()
                d["steps"][step.identifier] = {
                    "applicable": applicable,
                    "valid": valid,
                }

        return d


class CheckoutViewSet(viewsets.ViewSet):
    queryset = CheckoutSession.objects.none()
    lookup_url_kwarg = "cart_id"
    lookup_field = "cart_id"
    permission_classes = [
        StorefrontEventPermission,
    ]

    def _return_checkout_status(self, cs: CheckoutSession, status=200):
        serializer = CheckoutSessionSerializer(
            instance=cs,
            context={
                "event": self.request.event,
                "request": self.request,
            },
        )
        return Response(
            serializer.data,
            status=status,
        )

    def create(self, request, *args, **kwargs):
        if (
            request.event.presale_start
            and time_machine_now() < request.event.presale_start
        ):
            raise ValidationError(error_messages["not_started"])
        if request.event.presale_has_ended:
            raise ValidationError(error_messages["ended"])

        cs = CheckoutSession.objects.create(
            event=request.event,
            cart_id=generate_cart_id(),
            sales_channel=request.sales_channel,
            testmode=request.event.testmode,
            session_data={},
        )
        return self._return_checkout_status(cs, status=201)

    def retrieve(self, request, *args, **kwargs):
        cs = get_object_or_404(
            self.request.event.checkout_sessions, cart_id=kwargs["cart_id"]
        )
        return self._return_checkout_status(cs, status=200)

    @action(detail=True, methods=["GET", "PUT"])
    def addons(self, request, *args, **kwargs):
        cs = get_object_or_404(
            self.request.event.checkout_sessions, cart_id=kwargs["cart_id"]
        )
        groups = get_addon_groups(
            self.request.event,
            self.request.sales_channel,
            cs.customer,
            CartPosition.objects.filter(cart_id=cs.cart_id),
        )
        ctx = {
            "event": self.request.event,
        }

        if request.method == "PUT":
            serializer = CartAddonLineSerializer(
                data=request.data.get("lines", []),
                many=True,
                context={
                    "event": self.request.event,
                    "cart_id": cs.cart_id,
                },
            )
            serializer.is_valid(raise_exception=True)
            # todo: early validation, validate_cart_addons?
            return self._do_async(
                cs,
                set_cart_addons,
                self.request.event.pk,
                serializer.validated_data,
                [],
                cs.cart_id,
                locale=translation.get_language(),
                invoice_address=(
                    cs.invoice_address.pk if hasattr(cs, "invoice_address") else None
                ),
                sales_channel=cs.sales_channel.identifier,
                override_now_dt=time_machine_now(default=None),
            )
        elif request.method == "GET":
            data = [
                {
                    "parent": MinimalCartPositionSerializer(
                        grp["pos"], context=ctx
                    ).data,
                    "categories": [
                        {
                            "category": CategorySerializer(
                                cat["category"], context=ctx
                            ).data,
                            "multi_allowed": cat["multi_allowed"],
                            "min_count": cat["min_count"],
                            "max_count": cat["max_count"],
                            "items": ItemSerializer(
                                cat["items"],
                                many=True,
                                context={
                                    **ctx,
                                    "price_included": cat["price_included"],
                                    "max_count": (
                                        cat["max_count"] if cat["multi_allowed"] else 1
                                    ),
                                },
                            ).data,
                        }
                        for cat in grp["categories"]
                    ],
                }
                for grp in groups
            ]
            return Response(
                data={
                    "groups": data,
                },
                status=200,
            )

    def _get_total(self, cs, payments):
        cartpos = cs.get_cart_positions(prefetch_questions=True)
        total = sum(p.price for p in cartpos)

        try:
            # TODO: do we need a different get_fees for storefrontapi?
            fees = get_fees(
                self.request.event,
                self.request,
                total,
                (cs.invoice_address if hasattr(cs, "invoice_address") else None),
                payments=payments,
                positions=cartpos,
            )
        except TaxRule.SaleNotAllowed:
            # ignore for now, will fail on order creation
            fees = []

        total += sum([f.value for f in fees])
        return total

    @action(detail=True, methods=["GET", "POST"])
    def payment(self, request, *args, **kwargs):
        cs = get_object_or_404(
            self.request.event.checkout_sessions, cart_id=kwargs["cart_id"]
        )
        if request.method == "POST":
            # TODO: allow explicit removal

            for provider in self.request.event.get_payment_providers().values():
                if provider.identifier == request.data.get("identifier", ""):
                    if not provider.multi_use_supported:
                        # Providers with multi_use_supported will call this themselves
                        simulated_payments = cs.session_data.get("payments", {})
                        simulated_payments = [
                            p
                            for p in simulated_payments
                            if p.get("multi_use_supported")
                        ]
                        simulated_payments.append(
                            {
                                "provider": provider.identifier,
                                "multi_use_supported": False,
                                "min_value": None,
                                "max_value": None,
                                "info_data": {},
                            }
                        )
                        total = self._get_total(
                            cs,
                            simulated_payments,
                        )
                    else:
                        total = self._get_total(
                            cs,
                            [
                                p
                                for p in cs.session_data.get("payments", [])
                                if p.get("multi_use_supported")
                            ],
                        )

                    resp = provider.storefrontapi_prepare(
                        cs.session_data,
                        total,
                        request.data.get("info"),
                    )
                    if provider.multi_use_supported:
                        if resp is True:
                            # Provider needs to call add_payment_to_cart itself, but we need to remove all previously
                            # selected ones that don't have multi_use supported. Otherwise, if you first select a credit
                            # card, then go back and switch to a gift card, you'll have both in the session and the credit
                            # card has preference, which is unexpected.
                            cs.session_data["payments"] = [
                                p
                                for p in cs.session_data.get("payments", [])
                                if p.get("multi_use_supported")
                            ]

                            if provider.identifier not in [
                                p["provider"]
                                for p in cs.session_data.get("payments", [])
                            ]:
                                raise ImproperlyConfigured(
                                    f"Payment provider {provider.identifier} set multi_use_supported "
                                    f"and returned True from payment_prepare, but did not call "
                                    f"add_payment_to_cart"
                                )
                    else:
                        if resp is True or isinstance(resp, str):
                            # There can only be one payment method that does not have multi_use_supported, remove all
                            # previous ones.
                            cs.session_data["payments"] = [
                                p
                                for p in cs.session_data.get("payments", [])
                                if p.get("multi_use_supported")
                            ]
                            add_payment_to_cart_session(
                                cs.session_data, provider, None, None, None
                            )
                    cs.save(update_fields=["session_data"])
            return self._return_checkout_status(cs, 200)
        elif request.method == "GET":
            available_providers = []
            total = self._get_total(
                cs,
                [
                    p
                    for p in cs.session_data.get("payments", [])
                    if p.get("multi_use_supported")
                ],
            )

            for provider in sorted(
                self.request.event.get_payment_providers().values(),
                key=lambda p: (-p.priority, str(p.public_name).title()),
            ):
                # TODO: do we need a different is_allowed for storefrontapi?
                if not provider.is_enabled or not provider.is_allowed(
                    self.request, total
                ):
                    continue
                fee = provider.calculate_fee(total)
                available_providers.append(
                    {
                        "identifier": provider.identifier,
                        "label": provider.public_name,
                        "fee": str(fee),
                        "total": str(total + fee),
                    }
                )

            return Response(
                data={
                    "available_providers": available_providers,
                },
                status=200,
            )

    @action(detail=True, methods=["PATCH"])
    def fields(self, request, *args, **kwargs):
        cs = get_object_or_404(
            self.request.event.checkout_sessions, cart_id=kwargs["cart_id"]
        )
        server_pos = {p.pk: p for p in cs.get_cart_positions(prefetch_questions=True)}
        for req_pos in request.data.get("cart_positions", []):
            pos = server_pos[req_pos["id"]]
            fields = get_position_fields(self.request.event, pos)
            fields_data = req_pos["fields_data"]
            for f in fields:
                if f.identifier in fields_data:
                    # todo: validation error handing
                    value = f.validate_input(fields_data[f.identifier])
                    f.save_input(pos, value)

        fields = get_checkout_fields(self.request.event)
        fields_data = request.data.get("fields_data", {})
        session_data = cs.session_data
        for f in fields:
            if f.identifier in fields_data:
                # todo: validation error handing
                value = f.validate_input(fields_data[f.identifier])
                f.save_input(session_data, value)

        cs.session_data = session_data
        cs.save(update_fields=["session_data"])
        cs.refresh_from_db()
        return self._return_checkout_status(cs, 200)

    @action(detail=True, methods=["POST"])
    def add_to_cart(self, request, *args, **kwargs):
        cs = get_object_or_404(
            self.request.event.checkout_sessions, cart_id=kwargs["cart_id"]
        )
        serializer = CartAddLineSerializer(
            data=request.data.get("lines", []),
            many=True,
            context={
                "event": self.request.event,
            },
        )
        serializer.is_valid(raise_exception=True)
        return self._do_async(
            cs,
            add_items_to_cart,
            self.request.event.pk,
            serializer.validated_data,
            cs.cart_id,
            translation.get_language(),
            cs.invoice_address.pk if hasattr(cs, "invoice_address") else None,
            {},
            cs.sales_channel.identifier,
            time_machine_now(default=None),
        )

    @action(detail=True, methods=["POST"])
    def confirm(self, request, *args, **kwargs):
        cs = get_object_or_404(
            self.request.event.checkout_sessions, cart_id=kwargs["cart_id"]
        )
        cartpos = cs.get_cart_positions(prefetch_questions=True)
        total = sum(p.price for p in cartpos)

        try:
            fees = get_fees(
                self.request.event,
                self.request,
                total,
                (cs.invoice_address if hasattr(cs, "invoice_address") else None),
                payments=[],  # todo
                positions=cartpos,
            )
        except TaxRule.SaleNotAllowed as e:
            raise ValidationError(str(e))  # todo: need better message?

        total += sum([f.value for f in fees])
        steps = get_steps(
            request.event,
            cartpos,
            getattr(cs, "invoice_address", None),
            cs.session_data,
            total,
        )
        for step in steps:
            applicable = step.is_applicable()
            valid = not applicable or step.is_valid()
            if not valid:
                raise ValidationError(f"Step {step.identifier} is not valid")

        # todo: confirm messages, or integrate them as fields?
        meta_info = {
            "contact_form_data": cs.session_data.get("contact_form_data", {}),
        }
        api_meta = {}
        for receiver, response in order_meta_from_request.send(
            sender=request.event, request=request
        ):
            meta_info.update(response)
        for receiver, response in order_api_meta_from_request.send(
            sender=request.event, request=request
        ):
            api_meta.update(response)

        # todo: delete checkout session
        # todo: give info about order
        return self._do_async(
            cs,
            perform_order,
            self.request.event.id,
            payments=cs.session_data.get("payments", []),
            positions=[p.id for p in cartpos],
            email=cs.session_data.get("email"),
            locale=translation.get_language(),
            address=cs.invoice_address.pk if hasattr(cs, "invoice_address") else None,
            meta_info=meta_info,
            sales_channel=request.sales_channel.identifier,
            shown_total=None,
            customer=cs.customer,
            override_now_dt=time_machine_now(default=None),
            api_meta=api_meta,
        )

    @action(
        detail=True,
        methods=["GET"],
        url_name="task_status",
        url_path="task/(?P<asyncid>[^/]+)",
    )
    def task_status(self, *args, **kwargs):
        cs = get_object_or_404(
            self.request.event.checkout_sessions, cart_id=kwargs["cart_id"]
        )
        res = AsyncResult(kwargs["asyncid"])
        if res.ready():
            if res.successful() and not isinstance(res.info, Exception):
                return self._async_success(res, cs)
            else:
                return self._async_error(res, cs)
        return self._async_pending(res, cs)

    def _do_async(self, cs, task, *args, **kwargs):
        try:
            res = task.apply_async(args=args, kwargs=kwargs)
        except ConnectionError:
            # Task very likely not yet sent, due to redis restarting etc. Let's try once again
            res = task.apply_async(args=args, kwargs=kwargs)

        if res.ready():
            if res.successful() and not isinstance(res.info, Exception):
                return self._async_success(res, cs)
            else:
                return self._async_error(res, cs)
        return self._async_pending(res, cs)

    def _async_success(self, res, cs):
        return Response(
            {
                "status": "ok",
                "checkout_session": self._return_checkout_status(cs).data,
            },
            status=status.HTTP_200_OK,
        )

    def _async_error(self, res, cs):
        if isinstance(res.info, dict) and res.info["exc_type"] in [
            "OrderError",
            "CartError",
        ]:
            message = res.info["exc_message"]
        elif res.info.__class__.__name__ in ["OrderError", "CartError"]:
            message = str(res.info)
        else:
            logger.error("Unexpected exception: %r" % res.info)
            message = _("An unexpected error has occurred, please try again later.")

        return Response(
            {
                "status": "error",
                "message": message,
            },
            status=status.HTTP_409_CONFLICT,  # todo: find better status code
        )

    def _async_pending(self, res, cs):
        return Response(
            {
                "status": "pending",
                "check_url": reverse(
                    "storefrontapi-v1:checkoutsession-task_status",
                    kwargs={
                        "organizer": self.request.organizer.slug,
                        "event": self.request.event.slug,
                        "cart_id": cs.cart_id,
                        "asyncid": res.id,
                    },
                    request=self.request,
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )
