from typing import Any

from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, ListView, CreateView, UpdateView
from pretix.base.pdf import get_images, get_variables
from pretix.control.permissions import EventPermissionRequiredMixin
from .styles import PassLayout, get_platform_styles, get_platforms
from .models import WalletLayout
import json
from django.utils.translation import gettext_lazy as _
from django import forms
from django.core.exceptions import ValidationError
from i18nfield.fields import I18nCharField
from i18nfield.forms import I18nModelForm
from pretix.api.serializers.i18n import I18nAwareModelSerializer
from rest_framework import serializers
from rest_framework.renderers import JSONRenderer
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



class LayoutEditForm(forms.ModelForm):
    style = forms.ChoiceField()

    def __init__(self, **kwargs):
        self.platform = kwargs.pop('platform')
        super().__init__(**kwargs)

    class Meta:
        model = WalletLayout
        fields = ("name","style","layout")

    def __init__(self, event, platform, **kwargs):
        super().__init__(**kwargs)
        self.event = event
        self.platform = platform
        self.platform_styles = get_platform_styles(platform)
        self.fields["style"].choices = [
            (id, style.name) for id, style in self.platform_styles.items()
        ]

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
                style=self.coerce_style(self.cleaned_data["style"]), layout=self.cleaned_data["layout"]
            )
            layout.validate(self.event)
        return self.cleaned_data

class LayoutSerializer(I18nAwareModelSerializer):
    # # TODO: only necessary if we save through this serializer
    # style = serializers.ChoiceField(choices={})

    # def __init__(self, *args, platform, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.platform = platform
    #     self.platform_styles = get_platform_styles(platform)
    #     self.fields["style"].choices = [
    #         (id, style.name) for id, style in self.platform_styles.items()
    #     ]


    class Meta:
        model = WalletLayout
        fields = ("name","style","layout")

class LayoutEditorView(EventPermissionRequiredMixin, UpdateView):
    template_name = "pretixplugins/wallet/edit.html"
    form_class = LayoutEditForm
    model = WalletLayout
    permission = "can_change_event_settings" # TODO: new permission name
    pk_url_kwarg = "layout"

    @property
    def platform(self):
        return self.kwargs["platform"]

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
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
        if self.request.method == "POST":
            form = self.get_form()
            if not form.is_valid():
                layout_data = LayoutSerializer(self.object).data
                layout_data.update(form.cleaned_data)
                context['layout'] = layout_data
            else:
                context["layout"] = LayoutSerializer(self.object).data
        else:
            context["layout"] = LayoutSerializer(self.object).data

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

    def get_success_url(self) -> str:
        return reverse(
            "plugins:wallet:edit",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
                "platform": self.platform,
                "layout": self.object.pk,
            },
        )


class LayoutCreateView(LayoutEditorView):
    def get_object(self, queryset=None):
        return WalletLayout(event=self.request.event, platform=self.platform)