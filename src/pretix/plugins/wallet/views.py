from typing import Any

from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, ListView, TemplateView
from pretix.base.pdf import get_variables
from pretix.control.permissions import EventPermissionRequiredMixin
from .styles import PassLayout, get_platform_styles, get_platforms
from .models import WalletLayout
import json
from django.utils.translation import gettext_lazy as _
from django import forms
from django.core.exceptions import ValidationError


class LayoutListView(EventPermissionRequiredMixin, ListView):
    model = WalletLayout
    permission = "can_change_event_settings"
    template_name = "pretixplugins/wallet/layout_list.html"
    context_object_name = "layouts"

    def get_queryset(self):
        return self.request.event.wallet_layouts

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["platforms"] = get_platforms()
        return ctx


class EditorForm(forms.Form):
    name = forms.CharField()
    style = forms.TypedChoiceField()
    layout = forms.JSONField(initial={})

    def __init__(self, platform, **kwargs):
        super().__init__(**kwargs)
        self.platform = platform
        self.platform_styles = get_platform_styles(platform)
        self.fields["style"].choices = [
            (id, style.name) for id, style in self.platform_styles.items()
        ]
        self.fields["style"].coerce = self.coerce_style

    def coerce_style(self, value):
        return self.platform_styles[value]

    def clean_layout(self):
        layout = self.cleaned_data["layout"]

        if not isinstance(layout, dict):
            raise ValidationError(_("Layout must be a dict"))
        return layout

    def clean(self):
        if "style" in self.cleaned_data and "layout" in self.cleaned_data:
            layout = PassLayout(
                style=self.cleaned_data["style"], layout=self.cleaned_data["layout"]
            )
            layout.validate()
        return self.cleaned_data


class EditorView(EventPermissionRequiredMixin, FormView):
    template_name = "pretixplugins/wallet/edit.html"
    form_class = EditorForm
    success_url = ""
    permission = "can_change_event_settings"

    @property
    def platform(self):
        return self.kwargs["platform"]

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["platform"] = self.platform
        return kwargs

    def get_platform_styles(self):
        if self.platform not in get_platforms():
            raise Http404(
                _("Unknown platform '{platform}'").format(platform=self.platform)
            )
        return get_platform_styles(self.platform)

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["styles"] = {
            id: style.asdict() for id, style in self.get_platform_styles().items()
        }
        context["variables"] = {
            "text": {
                varname: {"label": var["label"], "editor_sample": var["editor_sample"]}
                for varname, var in get_variables(self.request.event).items()
            }
        }
        return context

    def form_valid(self, form):
        self.object = WalletLayout.objects.create(
            event=self.request.event,
            name=form.cleaned_data["name"],
            platform=self.platform,
            style=form.cleaned_data["style"],
            layout=form.cleaned_data["layout"],
        )
        return redirect(
            reverse(
                "plugins:wallet:edit",
                kwargs={
                    "organizer": self.request.event.organizer.slug,
                    "event": self.request.event.slug,
                    "platform": self.platform,
                    "layout": self.object.pk,
                },
            )
        )
