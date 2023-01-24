#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
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

import json
from json.decoder import JSONDecodeError

from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect,
)
from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from pretix.base.models import CartPosition, Discount
from pretix.control.forms.discounts import DiscountForm
from pretix.control.permissions import (
    EventPermissionRequiredMixin, event_permission_required,
)
from pretix.helpers.models import modelcopy

from ...base.channels import get_all_sales_channels
from ...helpers.compat import CompatDeleteView
from . import CreateView, PaginationMixin, UpdateView


class DiscountDelete(EventPermissionRequiredMixin, CompatDeleteView):
    model = Discount
    template_name = 'pretixcontrol/items/discount_delete.html'
    permission = 'can_change_items'
    context_object_name = 'discount'

    def get_context_data(self, *args, **kwargs) -> dict:
        context = super().get_context_data(*args, **kwargs)
        context['possible'] = self.object.allow_delete()
        return context

    def get_object(self, queryset=None) -> Discount:
        try:
            return self.request.event.discounts.get(
                id=self.kwargs['discount']
            )
        except Discount.DoesNotExist:
            raise Http404(_("The requested discount does not exist."))

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        if self.object.allow_delete():
            CartPosition.objects.filter(discount=self.object).update(discount=None)
            self.object.log_action('pretix.event.discount.deleted', user=self.request.user)
            self.object.delete()
            messages.success(request, _('The selected discount has been deleted.'))
        else:
            o = self.get_object()
            o.active = False
            o.save()
            o.log_action('pretix.event.discount.changed', user=self.request.user, data={
                'active': False
            })
            messages.success(request, _('The selected discount has been deactivated.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.items.discounts', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class DiscountUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Discount
    form_class = DiscountForm
    template_name = 'pretixcontrol/items/discount.html'
    permission = 'can_change_items'
    context_object_name = 'discount'

    def get_object(self, queryset=None) -> Discount:
        url = resolve(self.request.path_info)
        try:
            return self.request.event.discounts.get(
                id=url.kwargs['discount']
            )
        except Discount.DoesNotExist:
            raise Http404(_("The requested discount does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.event.discount.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.items.discounts', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.request.event
        return kwargs

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class DiscountCreate(EventPermissionRequiredMixin, CreateView):
    model = Discount
    form_class = DiscountForm
    template_name = 'pretixcontrol/items/discount.html'
    permission = 'can_change_items'
    context_object_name = 'discount'

    def get_success_url(self) -> str:
        return reverse('control:event.items.discounts', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, 'object', None):
            try:
                return self.request.event.discounts.get(pk=self.request.GET.get("copy_from"))
            except Discount.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            kwargs['instance'] = i
        else:
            kwargs['instance'] = Discount(event=self.request.event)

        kwargs['event'] = self.request.event
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        form.instance.position = (self.request.event.discounts.aggregate(m=Max('position'))['m'] or 0) + 1
        messages.success(self.request, _('The new discount has been created.'))
        ret = super().form_valid(form)
        form.instance.log_action('pretix.event.discount.added', data=dict(form.cleaned_data), user=self.request.user)
        return ret

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class DiscountList(PaginationMixin, ListView):
    model = Discount
    context_object_name = 'discounts'
    template_name = 'pretixcontrol/items/discounts.html'

    def get_queryset(self):
        return self.request.event.discounts.prefetch_related('condition_limit_products')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sales_channels'] = get_all_sales_channels()
        return ctx


def discount_move(request, discount, up=True):
    """
    This is a helper function to avoid duplicating code in discount_move_up and
    discount_move_down. It takes a discount and a direction and then tries to bring
    all discounts for this event in a new order.
    """
    try:
        discount = request.event.discounts.get(
            id=discount
        )
    except Discount.DoesNotExist:
        raise Http404(_("The requested discount does not exist."))
    discounts = list(request.event.discounts.order_by("position"))

    index = discounts.index(discount)
    if index != 0 and up:
        discounts[index - 1], discounts[index] = discounts[index], discounts[index - 1]
    elif index != len(discounts) - 1 and not up:
        discounts[index + 1], discounts[index] = discounts[index], discounts[index + 1]

    for i, d in enumerate(discounts):
        if d.position != i:
            d.position = i
            d.save()
    messages.success(request, _('The order of discounts has been updated.'))


@event_permission_required("can_change_items")
@require_http_methods(["POST"])
def discount_move_up(request, organizer, event, discount):
    discount_move(request, discount, up=True)
    return redirect('control:event.items.discounts',
                    organizer=request.event.organizer.slug,
                    event=request.event.slug)


@event_permission_required("can_change_items")
@require_http_methods(["POST"])
def discount_move_down(request, organizer, event, discount):
    discount_move(request, discount, up=False)
    return redirect('control:event.items.discounts',
                    organizer=request.event.organizer.slug,
                    event=request.event.slug)


@transaction.atomic
@event_permission_required("can_change_items")
@require_http_methods(["POST"])
def reorder_discounts(request, organizer, event):
    try:
        ids = json.loads(request.body.decode('utf-8'))['ids']
    except (JSONDecodeError, KeyError, ValueError):
        return HttpResponseBadRequest("expected JSON: {ids:[]}")

    input_discounts = list(request.event.discounts.filter(id__in=[i for i in ids if i.isdigit()]))

    if len(input_discounts) != len(ids):
        raise Http404(_("Some of the provided object ids are invalid."))

    if len(input_discounts) != request.event.discounts.count():
        raise Http404(_("Not all discounts have been selected."))

    for c in input_discounts:
        pos = ids.index(str(c.pk))
        if pos != c.position:  # Save unneccessary UPDATE queries
            c.position = pos
            c.save(update_fields=['position'])

    return HttpResponse()
