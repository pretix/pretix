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

# This file is based on an earlier version of pretix which was released under the Apache License 2.0. The full text of
# the Apache License 2.0 can be obtained at <http://www.apache.org/licenses/LICENSE-2.0>.
#
# This file may have since been changed and any changes are released under the terms of AGPLv3 as described above. A
# full history of changes and contributors is available at <https://github.com/pretix/pretix>.
#
# This file contains Apache-licensed contributions copyrighted by: Mason Mohkami, Sohalt, Tobias Kunze,
# jasonwaiting@live.hk, koebi
#
# Unless required by applicable law or agreed to in writing, software distributed under the Apache License 2.0 is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.

import io

import bleach
from defusedcsv import csv
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Sum
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView, ListView, TemplateView, UpdateView, View,
)
from django_scopes import scopes_disabled

from pretix.base.email import get_available_placeholders
from pretix.base.models import (
    CartPosition, LogEntry, Voucher, WaitingListEntry,
)
from pretix.base.models.vouchers import generate_codes
from pretix.base.services.locking import NoLockManager
from pretix.base.services.vouchers import vouchers_send
from pretix.base.templatetags.rich_text import markdown_compile_email
from pretix.base.views.tasks import AsyncFormView
from pretix.control.forms.filter import VoucherFilterForm, VoucherTagFilterForm
from pretix.control.forms.vouchers import VoucherBulkForm, VoucherForm
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.control.signals import voucher_form_class
from pretix.control.views import PaginationMixin
from pretix.helpers.compat import CompatDeleteView
from pretix.helpers.format import format_map
from pretix.helpers.models import modelcopy


class VoucherList(PaginationMixin, EventPermissionRequiredMixin, ListView):
    model = Voucher
    context_object_name = 'vouchers'
    template_name = 'pretixcontrol/vouchers/index.html'
    permission = 'can_view_vouchers'

    @scopes_disabled()  # we have an event check here, and we can save some performance on subqueries
    def get_queryset(self):
        qs = Voucher.annotate_budget_used_orders(self.request.event.vouchers.exclude(
            Exists(WaitingListEntry.objects.filter(voucher_id=OuterRef('pk')))
        ).select_related(
            'item', 'variation', 'seat'
        ))
        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return VoucherFilterForm(data=self.request.GET, event=self.request.event)

    def get(self, request, *args, **kwargs):
        if request.GET.get("download", "") == "yes":
            return self._download_csv()
        return super().get(request, *args, **kwargs)

    def _download_csv(self):
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

        headers = [
            _('Voucher code'), _('Valid until'), _('Product'), _('Reserve quota'), _('Bypass quota'),
            _('Price effect'), _('Value'), _('Tag'), _('Redeemed'), _('Maximum usages'), _('Seat'),
            _('Comment')
        ]
        writer.writerow(headers)

        for v in self.get_queryset():
            if v.item:
                if v.variation:
                    prod = '%s – %s' % (str(v.item), str(v.variation))
                else:
                    prod = '%s' % str(v.item)
            elif v.quota:
                prod = _('Any product in quota "{quota}"').format(quota=str(v.quota.name))
            else:
                prod = _('Any product')
            row = [
                v.code,
                v.valid_until.isoformat() if v.valid_until else "",
                prod,
                _("Yes") if v.block_quota else _("No"),
                _("Yes") if v.allow_ignore_quota else _("No"),
                v.get_price_mode_display(),
                str(v.value) if v.value is not None else "",
                v.tag,
                str(v.redeemed),
                str(v.max_usages),
                str(v.seat) if v.seat else "",
                str(v.comment) if v.comment else ""
            ]
            writer.writerow(row)

        r = HttpResponse(output.getvalue().encode("utf-8"), content_type='text/csv')
        r['Content-Disposition'] = 'attachment; filename="vouchers.csv"'
        return r


class VoucherTags(EventPermissionRequiredMixin, TemplateView):
    template_name = 'pretixcontrol/vouchers/tags.html'
    permission = 'can_view_vouchers'

    def get_queryset(self):
        qs = self.request.event.vouchers.order_by('tag').filter(
            tag__isnull=False,
            waitinglistentries__isnull=True
        )

        if self.filter_form.is_valid():
            qs = self.filter_form.filter_qs(qs)

        qs = qs.values('tag').annotate(
            total=Sum('max_usages'),
            redeemed=Sum('redeemed')
        )

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        tags = self.get_queryset()

        for t in tags:
            if t['total'] == 0:
                t['percentage'] = 0
            else:
                t['percentage'] = int((t['redeemed'] / t['total']) * 100)

        ctx['tags'] = tags
        ctx['filter_form'] = self.filter_form
        return ctx

    @cached_property
    def filter_form(self):
        return VoucherTagFilterForm(data=self.request.GET, event=self.request.event)


class VoucherDeleteCarts(EventPermissionRequiredMixin, CompatDeleteView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/delete_carts.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def get_object(self, queryset=None) -> Voucher:
        try:
            return self.request.event.vouchers.get(
                id=self.kwargs['voucher']
            )
        except Voucher.DoesNotExist:
            raise Http404(_("The requested voucher does not exist."))

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        self.object.log_action('pretix.voucher.carts.deleted', user=self.request.user)
        CartPosition.objects.filter(addon_to__voucher=self.object).delete()
        self.object.cartposition_set.all().delete()
        messages.success(request, _('The selected cart positions have been removed.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class VoucherDelete(EventPermissionRequiredMixin, CompatDeleteView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/delete.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def get_object(self, queryset=None) -> Voucher:
        try:
            return self.request.event.vouchers.get(
                id=self.kwargs['voucher']
            )
        except Voucher.DoesNotExist:
            raise Http404(_("The requested voucher does not exist."))

    def get(self, request, *args, **kwargs):
        if not self.get_object().allow_delete():
            messages.error(request, _('A voucher can not be deleted if it already has been redeemed.'))
            return HttpResponseRedirect(self.get_success_url())
        return super().get(request, *args, **kwargs)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()

        if not self.object.allow_delete():
            messages.error(request, _('A voucher can not be deleted if it already has been redeemed.'))
        else:
            self.object.log_action('pretix.voucher.deleted', user=self.request.user)
            CartPosition.objects.filter(addon_to__voucher=self.object).delete()
            self.object.cartposition_set.all().delete()
            self.object.delete()
            messages.success(request, _('The selected voucher has been deleted.'))
        return HttpResponseRedirect(success_url)

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class VoucherUpdate(EventPermissionRequiredMixin, UpdateView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/detail.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def get_form_class(self):
        form_class = VoucherForm
        for receiver, response in voucher_form_class.send(self.request.event, cls=form_class):
            if response:
                form_class = response
        return form_class

    def get_object(self, queryset=None) -> VoucherForm:
        url = resolve(self.request.path_info)
        try:
            return self.request.event.vouchers.get(
                id=url.kwargs['voucher']
            )
        except Voucher.DoesNotExist:
            raise Http404(_("The requested voucher does not exist."))

    @transaction.atomic
    def form_valid(self, form):
        messages.success(self.request, _('Your changes have been saved.'))
        if form.has_changed():
            self.object.log_action(
                'pretix.voucher.changed', user=self.request.user, data={
                    k: form.cleaned_data.get(k) for k in form.changed_data
                }
            )
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        redeemed_in_carts = CartPosition.objects.filter(
            voucher=self.object, event=self.request.event,
            expires__gte=now()
        ).count()
        ctx['redeemed_in_carts'] = redeemed_in_carts
        return ctx


class VoucherCreate(EventPermissionRequiredMixin, CreateView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/detail.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)

    def get_form_class(self):
        form_class = VoucherForm
        for receiver, response in voucher_form_class.send(self.request.event, cls=form_class):
            if response:
                form_class = response
        return form_class

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = Voucher(event=self.request.event)
        return kwargs

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        ret = super().form_valid(form)
        url = reverse('control:event.voucher', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
            'voucher': self.object.pk
        })
        messages.success(self.request, mark_safe(_('The new voucher has been created: {code}').format(
            code=format_html('<a href="{url}">{code}</a>', url=url, code=self.object.code)
        )))
        form.instance.log_action('pretix.voucher.added', data=dict(form.cleaned_data), user=self.request.user)
        return ret

    def post(self, request, *args, **kwargs):
        # TODO: Transform this into an asynchronous call?
        with request.event.lock():
            return super().post(request, *args, **kwargs)


class VoucherGo(EventPermissionRequiredMixin, View):
    permission = 'can_view_vouchers'

    def get_voucher(self, code):
        return Voucher.objects.get(code__iexact=code, event=self.request.event)

    def get(self, request, *args, **kwargs):
        code = request.GET.get("code", "").strip()
        try:
            voucher = self.get_voucher(code)
            return redirect('control:event.voucher', event=request.event.slug, organizer=request.event.organizer.slug,
                            voucher=voucher.id)
        except Voucher.DoesNotExist:
            messages.error(request, _('There is no voucher with the given voucher code.'))
            return redirect('control:event.vouchers', event=request.event.slug, organizer=request.event.organizer.slug)


class VoucherBulkCreate(EventPermissionRequiredMixin, AsyncFormView):
    model = Voucher
    template_name = 'pretixcontrol/vouchers/bulk.html'
    permission = 'can_change_vouchers'
    context_object_name = 'voucher'

    def get_success_url(self, value) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    def get_error_url(self):
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })

    @cached_property
    def copy_from(self):
        if self.request.GET.get("copy_from") and not getattr(self, 'object', None):
            try:
                return self.request.event.vouchers.get(pk=self.request.GET.get("copy_from"))
            except Voucher.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.copy_from:
            i = modelcopy(self.copy_from)
            i.pk = None
            i.redeemed = 0
            kwargs['instance'] = i
        else:
            kwargs['instance'] = Voucher(event=self.request.event, code=None)
        return kwargs

    def get_async_form_kwargs(self, form_kwargs, organizer=None, event=None):
        if not form_kwargs.get('instance'):
            form_kwargs['instance'] = Voucher(event=self.request.event, code=None)
        return form_kwargs

    def async_form_valid(self, task, form):
        lockfn = NoLockManager
        if form.data.get('block_quota'):
            lockfn = self.request.event.lock
        batch_size = 500
        total_num = 1  # will be set later

        def set_progress(percent):
            if not task.request.called_directly:
                task.update_state(
                    state='PROGRESS',
                    meta={'value': percent}
                )

        def process_batch(batch_vouchers, voucherids):
            Voucher.objects.bulk_create(batch_vouchers)
            if not connection.features.can_return_rows_from_bulk_insert:
                from_db = list(self.request.event.vouchers.filter(code__in=[v.code for v in batch_vouchers]))
                batch_vouchers.clear()
                batch_vouchers += from_db

            log_entries = []
            for v in batch_vouchers:
                voucherids.append(v.pk)
                data = dict(form.cleaned_data)
                data['code'] = code
                data['bulk'] = True
                del data['codes']
                log_entries.append(
                    v.log_action('pretix.voucher.added', data=data, user=self.request.user, save=False)
                )
            LogEntry.objects.bulk_create(log_entries)
            form.post_bulk_save(batch_vouchers)
            batch_vouchers.clear()
            set_progress(len(voucherids) / total_num * (50. if form.cleaned_data['send'] else 100.))

        voucherids = []
        with lockfn(), transaction.atomic():
            if not form.is_valid():
                raise ValidationError(form.errors)
            total_num = len(form.cleaned_data['codes'])

            batch_vouchers = []
            for code in form.cleaned_data['codes']:
                if len(batch_vouchers) >= batch_size:
                    process_batch(batch_vouchers, voucherids)

                obj = modelcopy(form.instance, code=None)
                obj.event = self.request.event
                obj.code = code
                try:
                    obj.seat = form.cleaned_data['seats'].pop()
                    obj.item = obj.seat.product
                except IndexError:
                    pass
                batch_vouchers.append(obj)

            process_batch(batch_vouchers, voucherids)

        if form.cleaned_data['send']:
            vouchers_send(
                event=self.request.event,
                vouchers=voucherids,
                subject=form.cleaned_data['send_subject'],
                message=form.cleaned_data['send_message'],
                recipients=[r._asdict() for r in form.cleaned_data['send_recipients']],
                user=self.request.user.pk,
                progress=lambda p: set_progress(50. + p * 50.)
            )

    def get_success_message(self, value):
        return _('The new vouchers have been created.')

    def get_form_class(self):
        form_class = VoucherBulkForm
        for receiver, response in voucher_form_class.send(self.request.event, cls=form_class):
            if response:
                form_class = response
        return form_class

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['code_length'] = settings.ENTROPY['voucher_code']
        return ctx

    def form_invalid(self, form):
        messages.error(self.request, _('We could not save your changes. See below for details.'))
        return super().form_invalid(form)


class VoucherBulkMailPreview(EventPermissionRequiredMixin, View):
    permission = 'can_change_vouchers'

    # return the origin text if key is missing in dict
    class SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'

    # get all supported placeholders with dummy values
    def placeholders(self, item):
        ctx = {}
        base_ctx = ['event', 'name']
        if item == 'send_message':
            base_ctx += ['voucher_list']
        for p in get_available_placeholders(self.request.event, base_ctx).values():
            s = str(p.render_sample(self.request.event))
            if s.strip().startswith('* ') or s.startswith('  '):
                ctx[p.identifier] = '<div class="placeholder" title="{}">{}</div>'.format(
                    _('This value will be replaced based on dynamic parameters.'),
                    markdown_compile_email(s)
                )
            else:
                ctx[p.identifier] = '<span class="placeholder" title="{}">{}</span>'.format(
                    _('This value will be replaced based on dynamic parameters.'),
                    s
                )
        return self.SafeDict(ctx)

    def post(self, request, *args, **kwargs):
        preview_item = request.POST.get('item', '')
        if preview_item not in ('send_message', 'send_subject'):
            return HttpResponseBadRequest(_('invalid item'))
        msgs = {}
        if "subject" in preview_item:
            msgs["all"] = format_map(bleach.clean(request.POST.get(preview_item, "")), self.placeholders(preview_item))
        else:
            msgs["all"] = markdown_compile_email(
                format_map(request.POST.get(preview_item), self.placeholders(preview_item))
            )

        return JsonResponse({
            'item': preview_item,
            'msgs': msgs
        })


class VoucherRNG(EventPermissionRequiredMixin, View):
    permission = 'can_change_vouchers'

    def get(self, request, *args, **kwargs):
        try:
            num = int(request.GET.get('num', '5'))
            if num > 100_000:
                return HttpResponseBadRequest()
        except ValueError:  # NOQA
            return HttpResponseBadRequest()

        prefix = request.GET.get('prefix')
        codes = generate_codes(request.organizer, num, prefix=prefix)
        return JsonResponse({
            'codes': codes
        })

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })


class VoucherBulkAction(EventPermissionRequiredMixin, View):
    permission = 'can_change_vouchers'

    @cached_property
    def objects(self):
        return self.request.event.vouchers.filter(
            id__in=self.request.POST.getlist('voucher')
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete':
            return render(request, 'pretixcontrol/vouchers/delete_bulk.html', {
                'allowed': self.objects.filter(redeemed=0),
                'forbidden': self.objects.exclude(redeemed=0),
            })
        elif request.POST.get('action') == 'delete_confirm':
            for obj in self.objects:
                if obj.allow_delete():
                    obj.log_action('pretix.voucher.deleted', user=self.request.user)
                    CartPosition.objects.filter(addon_to__voucher=obj).delete()
                    obj.cartposition_set.all().delete()
                    obj.delete()
                else:
                    obj.log_action('pretix.voucher.changed', user=self.request.user, data={
                        'max_usages': min(obj.redeemed, obj.max_usages),
                        'bulk': True
                    })
                    obj.max_usages = min(obj.redeemed, obj.max_usages)
                    obj.save(update_fields=['max_usages'])
            messages.success(request, _('The selected vouchers have been deleted or disabled.'))
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        return reverse('control:event.vouchers', kwargs={
            'organizer': self.request.event.organizer.slug,
            'event': self.request.event.slug,
        })
