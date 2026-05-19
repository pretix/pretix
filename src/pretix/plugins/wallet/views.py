import json
from typing import Any

from django import forms
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView
from pretix.base.pdf import get_images, get_variables
from pretix.control.permissions import EventPermissionRequiredMixin
from django.conf import settings
from .models import WalletLayout
from .styles import AVAILABLE_STYLES, AVAILABLE_PLATFORMS


def get_layout_variables(event):
    return {
        "text": get_variables(event),
        "image": get_images(event)
        | {"poweredby": {"label": _("pretix-Logo")}},  # TODO: image upload
    }


def get_editor_variables(event):
    return {
        t: {
            vid: {"label": v.get("label"), "editor_sample": v.get("editor_sample")}
            for vid, v in vs.items()
        }
        for t, vs in get_layout_variables(event).items()
    }


class LayoutListView(EventPermissionRequiredMixin, ListView):
    model = WalletLayout
    permission = "can_change_event_settings"
    template_name = "pretixplugins/wallet/layout_list.html"
    context_object_name = "layouts"

    def get_queryset(self):
        return self.request.event.wallet_layouts.all()


class LayoutEditorView(DetailView):
    template_name = "pretixplugins/wallet/edit.html"
    model = WalletLayout
    permission = "event.settings.general:write"
    pk_url_kwarg = "layout"

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['platforms'] = [{
                "identifier": platform.identifier,
                "name": platform.name,
                "styles": {
                    style.identifier: style.asdict() for style in AVAILABLE_STYLES.get(platform.identifier)
                }
            } for platform in AVAILABLE_PLATFORMS
        ]
        # context["styles"] = {
        #     style.identifier: style.asdict() for style in self.get_platform_styles()
        # }
        context["variables"] = get_editor_variables(self.request.event)
        context["locales"] = {
            l: dict(settings.LANGUAGES).get(l, l)
            for l in self.request.event.settings.get("locales")
        }

        return context


class WalletLayoutCreateForm(forms.ModelForm):
    class Meta:
        model = WalletLayout
        fields = ("name",)

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event

    def save(self, *args, **kwargs) -> Any:
        self.instance.event = self.event
        return super().save(*args, **kwargs)


class LayoutCreateView(CreateView):
    template_name = "pretixplugins/wallet/create.html"
    form_class = WalletLayoutCreateForm
    permission = "event.settings.general:write"

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
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
