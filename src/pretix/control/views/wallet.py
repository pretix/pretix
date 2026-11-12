import json
import os
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import BadRequest, ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    View,
)
from rest_framework import serializers, viewsets

from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.base.i18n import language
from pretix.base.middleware import add_to_response_csp
from pretix.base.models.orders import OrderPosition
from pretix.base.models.wallet import WalletLayout, WalletPlatformLayout
from pretix.base.services import tickets
from pretix.base.services.tickets import get_preview_position
from pretix.base.views.tasks import AsyncAction
from pretix.base.wallet.placeholders import (
    get_wallet_placeholder_renderer,
    get_wallet_placeholders,
)
from pretix.base.wallet.platforms import (
    get_available_platforms,
    get_platform,
    pass_style_registry,
    wallet_platform_registry,
)
from pretix.base.wallet.tasks import get_pass
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views.orders import OrderView
from pretix.helpers.database import rolledback_transaction
from pretix.helpers.i18n import localizable_to_dict
from pretix.helpers.models import modelclone
from pretix.plugins.wallet.forms import WalletLayoutCreateForm


class WalletPlatformLayoutSerializer(I18nAwareModelSerializer):
    platform = serializers.ChoiceField(choices=[])
    style = serializers.CharField(allow_null=True, required=False)
    file_settings = serializers.JSONField(default=dict, required=False)

    class Meta:
        model = WalletPlatformLayout
        fields = ("platform", "style", "layout", "file_settings")

    def get_fields(self):
        fields = super().get_fields()
        fields["platform"].choices = [
            p.identifier
            for p, _ in wallet_platform_registry.filter(active_in=self.context["event"])
        ]
        return fields

    def validate_layout(self, value):
        if not isinstance(value, dict):
            raise ValidationError(_("Layout must be a dict"))
        return value

    def validate(self, data):
        platform = data.get("platform")
        style = data.get("style")
        layout = data.get("layout")
        if platform and style and layout:
            style, _meta = pass_style_registry.get(
                active_in=self.context["event"], identifier=(platform, style)
            )
            if not style:
                raise ValidationError({"style": _("Invalid style")})

            obj = style(event=self.context["event"], layout=data["layout"])
            obj.validate()
            data["file_settings"] = obj.extract_file_settings(
                self.context["request"], data.get("file_settings", {})
            )

        return data

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["file_settings"] = {}
        for file_setting in instance.file_settings.all():
            try:
                url = file_setting.file.url
            except AttributeError:
                continue
            request = self.context["request"]
            ret["file_settings"][file_setting.key] = {
                "url": request.build_absolute_uri(url),
                "name": os.path.basename(file_setting.file.name).split(".", 1)[-1],
            }
        return ret


class WalletLayoutSerializer(I18nAwareModelSerializer):
    platform_layouts = WalletPlatformLayoutSerializer(many=True)

    class Meta:
        model = WalletLayout
        fields = ("id", "name", "platform_layouts")
        read_only_fields = ("id",)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs, event=self.context["event"])

    def update(self, instance, validated_data):
        platform_layouts = validated_data.pop("platform_layouts")
        for layout in platform_layouts:
            if layout["style"]:
                file_settings = layout.pop("file_settings", {})
                obj, _ = instance.platform_layouts.update_or_create(
                    platform=layout["platform"], defaults=layout
                )
                obj.file_settings.exclude(key__in=file_settings.keys()).delete()
                for key, file in file_settings.items():
                    if file != "keep":
                        file_setting, _ = obj.file_settings.get_or_create(key=key)
                        file_setting.file.save(os.path.basename(file.name), file)

        instance.platform_layouts.exclude(
            platform__in={
                layout["platform"]
                for layout in platform_layouts
                if layout["style"] is not None
            }
        ).delete()
        return super().update(instance, validated_data)


class WalletLayoutViewSet(viewsets.ModelViewSet):
    model = WalletLayout
    queryset = WalletLayout.objects.none()
    serializer_class = WalletLayoutSerializer
    permission = "event.settings.general:write"

    def get_queryset(self):
        return self.request.event.wallet_layouts.all()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["event"] = self.request.event
        return ctx

    @transaction.atomic()
    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance.log_action(
            action="pretix.plugins.wallet.layout.changed",
            user=self.request.user,
            auth=self.request.auth,
            data=serializer.to_representation(serializer.instance),
        )
        tickets.invalidate_cache.apply_async(
            kwargs={"event": self.request.event.pk, "provider": "wallet"}
        )


def get_editor_placeholders(event):
    with (
        rolledback_transaction(),
        language(event.settings.locale, event.settings.region),
    ):
        p = get_preview_position(event)
        context = get_wallet_placeholder_renderer(order_position=p)
        placeholders = {
            t: {
                pid: {
                    "label": (localizable_to_dict(p.label, event.settings.locales)),
                    "sample": str(context.render_sample(p)),
                    "required_context": list(sorted(p.required_context)),
                }
                for pid, p in ps.items()
            }
            for t, ps in get_wallet_placeholders(event).items()
        }
    return placeholders


class WalletLayoutMixin:
    model = WalletLayout
    permission = "event.settings.general:write"
    pk_url_kwarg = "layout"
    context_object_name = "layouts"

    def get_queryset(self):
        return self.request.event.wallet_layouts.all()


class LayoutListView(WalletLayoutMixin, EventPermissionRequiredMixin, ListView):
    template_name = "pretixcontrol/wallet/layout_list.html"


class LayoutDetailView(WalletLayoutMixin, EventPermissionRequiredMixin, DetailView):
    pass


class LayoutEditorView(LayoutDetailView):
    template_name = "pretixcontrol/wallet/edit.html"

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["platforms"] = [
            {
                "identifier": platform.identifier,
                "name": platform.name,
                "styles": {
                    style.identifier: style(self.request.event).asdict()
                    for style, _meta in pass_style_registry.filter(
                        active_in=self.request.event, platform=platform.identifier
                    )
                },
            }
            for platform in sorted(
                get_available_platforms(self.request.event, show_disabled=True),
                key=lambda x: x.identifier,
            )
        ]
        context["placeholders"] = get_editor_placeholders(self.request.event)
        context["locales"] = {
            l: dict(settings.LANGUAGES).get(l, l)
            for l in self.request.event.settings.get("locales")
        }

        return context

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        add_to_response_csp(
            response,
            {
                "img-src": ["blob:"],
            },
        )
        return response


class LayoutCreateView(WalletLayoutMixin, EventPermissionRequiredMixin, CreateView):
    template_name = "pretixcontrol/wallet/create.html"
    form_class = WalletLayoutCreateForm
    permission = "event.settings.general:write"

    def form_valid(self, form):
        self.object = form.save()
        self.object.log_action(
            action="pretix.plugins.wallet.layout.created",
            user=self.request.user,
            data={
                **form.cleaned_data,
                "copy_from": self.copy_from.pk if self.copy_from else None,
            },
        )
        if self.copy_from:
            for pl in self.copy_from.platform_layouts.all():
                modelclone(pl, parent=self.object).save()
        else:
            for platform, _meta in wallet_platform_registry.filter(active_in=self.request.event):
                if not platform.default_style:
                    continue
                style, _meta = pass_style_registry.get(active_in=self.request.event, identifier=(platform.identifier, platform.default_style))
                if not style:
                    continue
                layout = style(self.request.event).default_layout
                self.object.platform_layouts.get_or_create(platform=platform.identifier, defaults={"style": style.identifier, "layout": layout})

        return HttpResponseRedirect(self.get_success_url())

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event

        if self.copy_from:
            kwargs["instance"] = modelclone(self.copy_from, default=False)
            kwargs.setdefault("initial", {})

        return kwargs

    def get_success_url(self) -> str:
        return reverse(
            "plugins:wallet:edit",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
                "layout": self.object.pk,
            },
        )

    @cached_property
    def copy_from(self) -> WalletLayout | None:
        if self.request.GET.get("copy_from"):
            try:
                return self.get_queryset().get(pk=self.request.GET.get("copy_from"))
            except WalletLayout.DoesNotExist:
                pass


class LayoutPreviewView(EventPermissionRequiredMixin, View):
    permission = "event.settings.general:write"

    def post(self, request, **kwargs):
        event = request.event
        platform_id = request.POST.get("platform")
        style_id = request.POST.get("style")
        layout = request.POST.get("layout")
        file_settings = json.loads(request.POST.get("file_settings"))
        base_layout = (
            event.wallet_layouts.get(pk=request.POST.get("id"))
            .platform_layouts.filter(platform=platform_id)
            .first()
        )

        if base_layout:
            base_file_settings = {
                fs.key: fs.file for fs in base_layout.file_settings.all()
            }
        else:
            base_file_settings = {}

        platform = get_platform(event, platform_id, show_disabled=True)
        if not platform:
            raise BadRequest("Unknown platform")

        style, _meta = pass_style_registry.get(
            active_in=event, identifier=(platform_id, style_id)
        )
        if not style:
            raise BadRequest("Unknown style")

        layout = json.loads(layout)
        with (
            rolledback_transaction(),
            language(request.event.settings.locale, request.event.settings.region),
        ):
            p = get_preview_position(request.event)
            l = style(event=event, layout=layout)
            file_settings = {
                **base_file_settings,
                **l.extract_file_settings(request, file_settings),
            }
            layout = style(event, layout, file_settings)
            layout.validate()

            result = platform.generate_preview(p, layout)
            if isinstance(result, str):
                return redirect(result)
            else:
                ext, mimet, data = result
                resp = HttpResponse(
                    data,
                    content_type=mimet,
                    headers={
                        "Content-Disposition": 'attachment; filename="ticket-preview.{}"'.format(
                            ext.lstrip(".")
                        )
                    },
                )
            return resp


class LayoutSetDefault(LayoutDetailView):
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if not obj.default:
            for layout in request.event.wallet_layouts.filter(default=True):
                layout.log_action(
                    "pretix.plugins.wallet.layout.changed",
                    user=self.request.user,
                    data={
                        "default": False,
                    },
                )
                layout.default = False
                layout.save(update_fields=["default"])
            obj.log_action(
                "pretix.plugins.wallet.layout.changed",
                user=self.request.user,
                data={
                    "default": True,
                },
            )
            obj.default = True
            obj.save(update_fields=["default"])
            tickets.invalidate_cache.apply_async(
                kwargs={"event": self.request.event.pk, "provider": "wallet"}
            )
        messages.success(self.request, _("Your changes have been saved."))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse(
            "plugins:wallet:index",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


class LayoutDelete(WalletLayoutMixin, DeleteView):
    template_name = "pretixcontrol/wallet/delete.html"

    def get_success_url(self) -> str:
        return reverse(
            "plugins:wallet:index",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )

    @transaction.atomic
    def form_valid(self, form):
        self.object = self.get_object()
        if self.object.allow_delete():
            self.object.log_action(
                action="pretix.plugins.wallet.layout.deleted", user=self.request.user
            )
            self.object.delete()
            tickets.invalidate_cache.apply_async(
                kwargs={"event": self.request.event.pk, "provider": "wallet"}
            )
            messages.success(self.request, _("The selected layout been deleted."))
        else:
            messages.error(self.request, _("The selected layout cannot be deleted."))

        return redirect(self.get_success_url())


class OrderDownloadMixin:
    task = get_pass

    def get_success_message(self, value):
        return ""

    def get_success_url(self, value):
        return value

    @cached_property
    def platform(self):
        if platform := self.kwargs.get("platform"):
            return get_platform(self.request.event, platform, show_disabled=True)


class WalletGetView(OrderDownloadMixin, AsyncAction, OrderView):
    permission = "event.orders:read"

    def get_error_url(self):
        return self.get_order_url()

    @cached_property
    def order_position(self):
        try:
            return self.order.positions.get(pk=self.kwargs.get("position"))
        except OrderPosition.DoesNotExist:
            return None

    def post(self, request, *args, **kwargs):
        if not self.platform:
            return self.error(_("You requested an invalid wallet platform."))
        if not self.order_position:
            raise Http404(
                _("Unknown order code or not authorized to access this order.")
            )

        if "position" in kwargs:
            if not self.platform.is_available_for_position(self.order_position):
                return self.error(_("Ticket download is not enabled for this product."))
            return self.do(
                "orderposition", self.order_position.pk, self.platform.identifier, True
            )
        else:
            return self.do("order", self.order.pk, self.platform.identifier, True)
