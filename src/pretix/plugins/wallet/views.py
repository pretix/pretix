import json
from typing import Any

from django import forms
from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView, DetailView, ListView
)
from pretix.base.pdf import get_images, get_variables
from pretix.control.permissions import EventPermissionRequiredMixin

from .models import WalletLayout
from .styles import get_platform_styles, get_platforms


# TODO: should this even be a list view?
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


class LayoutEditorView(DetailView):
    template_name = "pretixplugins/wallet/edit.html"
    model = WalletLayout
    permission = "event.settings.general:write"
    pk_url_kwarg = "layout"

    def get_platform_styles(self):
        if self.object.platform not in get_platforms():
            raise Http404(
                _("Unknown platform '{platform}'").format(platform=self.object.platform)
            )
        return get_platform_styles(self.object.platform)

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["styles"] = {
            id: style.asdict() for id, style in self.get_platform_styles().items()
        }
        context["variables"] = {
            "text": {
                varname: {"label": var["label"], "editor_sample": var["editor_sample"]}
                for varname, var in get_variables(self.request.event).items()
            },
            "image": {
                varname: {"label": var['label']} for varname, var in get_images(self.request.event).items()
            } | {"poweredby": {"label": _("pretix-Logo")}} # TODO: image upload
        }
        return context

class WalletLayoutCreateForm(forms.ModelForm):
    class Meta:
        model = WalletLayout
        fields = ("name",)
    
    def __init__(self, *args, platform, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.platform = platform
        self.event = event

    def save(self, *args, **kwargs) -> Any:
        self.instance.platform = self.platform
        self.instance.event = self.event
        return super().save(*args, **kwargs)
    
class LayoutCreateView(CreateView):
    template_name = "pretixplugins/wallet/create.html"
    form_class = WalletLayoutCreateForm
    permission = "event.settings.general:write"

    @property
    def platform(self):
        platform = self.kwargs['platform']
        if platform not in get_platforms():
            raise Http404(
                _("Unknown platform '{platform}'").format(platform=platform)
            )
        return platform
    
    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs['platform'] = self.platform
        kwargs['event'] = self.request.event
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