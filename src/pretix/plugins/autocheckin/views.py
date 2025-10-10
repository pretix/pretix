#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020  Raphael Michel and contributors
# Copyright (C) 2020-today pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import DeleteView, ListView

from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.views import CreateView, UpdateView
from pretix.helpers.models import modelcopy
from pretix.plugins.autocheckin.forms import AutoCheckinRuleForm
from pretix.plugins.autocheckin.models import AutoCheckinRule


class IndexView(EventPermissionRequiredMixin, ListView):
    permission = "can_change_event_settings"
    template_name = "pretixplugins/autocheckin/index.html"
    paginate_by = 50
    context_object_name = "rules"

    def get_queryset(self):
        return (
            self.request.event.autocheckinrule_set.select_related(
                "list",
            )
            .prefetch_related(
                "limit_sales_channels",
                "limit_products",
                "limit_variations",
                "limit_variations__item",
            )
            .order_by(
                "list__name",
                "list_id",
                "pk",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sales_channels"] = self.request.organizer.sales_channels.all()

        pprovs = self.request.event.get_payment_providers()
        for r in ctx["rules"]:
            r.pprovs = [pprovs[p] for p in r.limit_payment_methods if p in pprovs]
        return ctx


class RuleAddView(EventPermissionRequiredMixin, CreateView):
    template_name = "pretixplugins/autocheckin/add.html"
    permission = "can_change_event_settings"
    form_class = AutoCheckinRuleForm
    model = AutoCheckinRule

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, "object", None):
            try:
                return AutoCheckinRule.objects.get(
                    pk=self.request.GET.get("copy_from"), event=self.request.event
                )
            except AutoCheckinRule.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event

        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            kwargs["instance"] = i
            kwargs.setdefault("initial", {})
            kwargs["initial"]["itemvars"] = [
                str(i.pk) for i in self.copy_from.limit_products.all()
            ] + [
                "{}-{}".format(v.item_id, v.pk)
                for v in self.copy_from.limit_variations.all()
            ]
            kwargs["initial"][
                "limit_payment_methods"
            ] = self.copy_from.limit_payment_methods
            kwargs["initial"][
                "limit_sales_channels"
            ] = self.copy_from.limit_sales_channels.all()
        return kwargs

    def form_invalid(self, form):
        messages.error(
            self.request, _("We could not save your changes. See below for details.")
        )
        return super().form_invalid(form)

    def form_valid(self, form):
        self.output = {}

        messages.success(self.request, _("Your rule has been created."))

        form.instance.event = self.request.event

        with transaction.atomic():
            self.object = form.save()
            form.instance.log_action(
                "pretix.plugins.autocheckin.rule.added",
                user=self.request.user,
                data=dict(form.cleaned_data),
            )

        return redirect(
            "plugins:autocheckin:edit",
            event=self.request.event.slug,
            organizer=self.request.event.organizer.slug,
            rule=self.object.pk,
        )


class RuleEditView(EventPermissionRequiredMixin, UpdateView):
    model = AutoCheckinRule
    form_class = AutoCheckinRuleForm
    template_name = "pretixplugins/autocheckin/edit.html"
    permission = "can_change_event_settings"

    def get_object(self, queryset=None) -> AutoCheckinRule:
        return get_object_or_404(
            AutoCheckinRule.objects.all(),
            event=self.request.event,
            id=self.kwargs["rule"],
        )

    def get_success_url(self):
        return reverse(
            "plugins:autocheckin:edit",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
                "rule": self.object.pk,
            },
        )

    @transaction.atomic()
    def form_valid(self, form):
        messages.success(self.request, _("Your changes have been saved."))
        form.instance.log_action(
            "pretix.plugins.autocheckin.rule.changed",
            user=self.request.user,
            data=dict(form.cleaned_data),
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request, _("We could not save your changes. See below for details.")
        )
        return super().form_invalid(form)


class RuleDeleteView(EventPermissionRequiredMixin, DeleteView):
    model = AutoCheckinRule
    permission = "can_change_event_settings"
    template_name = "pretixplugins/autocheckin/delete.html"
    context_object_name = "rule"

    def get_success_url(self):
        return reverse(
            "plugins:autocheckin:index",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )

    def get_object(self, queryset=None) -> AutoCheckinRule:
        return get_object_or_404(
            AutoCheckinRule, event=self.request.event, id=self.kwargs["rule"]
        )

    @transaction.atomic
    def form_valid(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        self.request.event.log_action(
            "pretix.plugins.autocheckin.rule.deleted", user=self.request.user, data={}
        )

        self.object.delete()
        messages.success(self.request, _("The selected rule has been deleted."))
        return redirect(success_url)
