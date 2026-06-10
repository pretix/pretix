import copy
import json
from typing import Any

from django.db import transaction
from django import forms
from django.core.exceptions import BadRequest
from django.db.models.query import QuerySet
from django.urls import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, DeleteView, View
from pretix.base.i18n import language
from pretix.base.pdf import get_images, get_variables
from pretix.base.services.tickets import get_preview_position
from pretix.control.permissions import EventPermissionRequiredMixin
from django.conf import settings
from django.shortcuts import redirect
from pretix.helpers.database import rolledback_transaction
from pretix.helpers.models import modelclone
from .models import WalletLayout
from .styles import AVAILABLE_STYLES, AVAILABLE_PLATFORMS, AVAILABLE_STYLES_DICT, PassLayout
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.utils.functional import cached_property

def get_layout_variables(event):
    return {
        "text": get_variables(event),
        "image": get_images(event)
        | {"poweredby": {"label": _("pretix-Logo"), "evaluate": lambda *_: open(finders.find("pretix_passbook/logo.png"), "rb")},
           "poweredby_icon": {"label": _("pretix-Icon"), "evaluate": lambda *_: open(finders.find("pretix_passbook/icon.png"), "rb")}},  # TODO: image upload
    }


def get_editor_variables(event):
    return {
        t: {
            vid: {"label": v.get("label"), "editor_sample": v.get("editor_sample")}
            for vid, v in vs.items()
        }
        for t, vs in get_layout_variables(event).items()
    }

class WalletLayoutMixin:
    model = WalletLayout
    permission = "event.settings.general:write"
    pk_url_kwarg = "layout"
    context_object_name = "layouts"

    def get_queryset(self):
        return self.request.event.wallet_layouts.all()

class LayoutListView(WalletLayoutMixin, EventPermissionRequiredMixin, ListView):
    template_name = "pretixplugins/wallet/layout_list.html"


class LayoutDetailView(WalletLayoutMixin, EventPermissionRequiredMixin, DetailView):
    pass


class LayoutEditorView(LayoutDetailView):
    template_name = "pretixplugins/wallet/edit.html"

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


class LayoutCreateView(WalletLayoutMixin, EventPermissionRequiredMixin, CreateView):
    template_name = "pretixplugins/wallet/create.html"
    form_class = WalletLayoutCreateForm
    permission = "event.settings.general:write"

    def form_valid(self, form):
        self.object = form.save()
        if self.copy_from:
            for pl in self.copy_from.platform_layouts.all():
                modelclone(pl, parent=self.object).save()
        return HttpResponseRedirect(self.get_success_url())
    
    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event

        if self.copy_from:
            kwargs['instance'] = modelclone(self.copy_from, default=False)
            kwargs.setdefault('initial', {})
            
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

        platform = None
        for p in AVAILABLE_PLATFORMS:
            if p.identifier == platform_id:
                platform = p
        if not platform:
            raise BadRequest("Unknown platform")
        if style_id not in AVAILABLE_STYLES_DICT[platform_id]:
            raise BadRequest("Unknown style")
        style = AVAILABLE_STYLES_DICT[platform_id][style_id]

        layout = json.loads(layout)
        with rolledback_transaction(), language(request.event.settings.locale, request.event.settings.region):
            p = get_preview_position(request.event)
            layout = PassLayout(style=style, layout=layout)
            context = {"placeholders": get_layout_variables(event)}
            layout.validate(context=context)

            fname, mimet, data = platform.generate(layout, p)
            resp = HttpResponse(data, content_type=mimet)
            ftype = fname.split(".")[-1]
            resp['Content-Disposition'] = 'attachment; filename="ticket-preview.{}"'.format(ftype)
            return resp
        


class LayoutSetDefault(LayoutDetailView):
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        request.event.wallet_layouts.exclude(pk=obj.pk).update(default=False)
        obj.default = True
        obj.save(update_fields=['default'])
        messages.success(self.request, _('Your changes have been saved.'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('plugins:wallet:index', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })



class LayoutDelete(WalletLayoutMixin, DeleteView):
    template_name = 'pretixplugins/wallet/delete.html'

    def get_success_url(self) -> str:
        return reverse('plugins:wallet:index', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @transaction.atomic
    def form_valid(self, form):
        self.object = self.get_object()
        self.object.log_action(action='pretix.plugins.wallet.layout.deleted', user=self.request.user)
        self.object.delete()

        if not self.request.event.wallet_layouts.filter(default=True).exists():
            f = self.request.event.wallet_layouts.first()
            if f:
                f.default = True
                f.save(update_fields=['default'])

        messages.success(self.request, _('The selected layout been deleted.'))
        return redirect(self.get_success_url())
