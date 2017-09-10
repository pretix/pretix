from collections import defaultdict
from datetime import timedelta
from itertools import groupby

from django.db.models import Sum
from django.utils.functional import cached_property
from django.utils.timezone import now

from pretix.base.models import CartPosition, InvoiceAddress, OrderPosition
from pretix.base.services.cart import get_fees
from pretix.presale.signals import question_form_fields


class CartMixin:
    @cached_property
    def positions(self):
        """
        A list of this users cart position
        """
        return list(get_cart(self.request))

    @cached_property
    def cart_session(self):
        from pretix.presale.views.cart import cart_session
        return cart_session(self.request)

    def get_cart(self, answers=False, queryset=None, order=None, downloads=False):
        if queryset:
            prefetch = []
            if answers:
                prefetch.append('item__questions')
                prefetch.append('answers')

            cartpos = queryset.order_by(
                'item', 'variation'
            ).select_related(
                'item', 'variation', 'addon_to', 'subevent', 'subevent__event', 'subevent__event__organizer'
            ).prefetch_related(
                *prefetch
            )
        else:
            cartpos = self.positions

        lcp = list(cartpos)
        has_addons = {cp.addon_to.pk for cp in lcp if cp.addon_to}

        pos_additional_fields = defaultdict(list)
        for cp in lcp:
            responses = question_form_fields.send(sender=self.request.event, position=cp)
            data = cp.meta_info_data
            for r, response in sorted(responses, key=lambda r: str(r[0])):
                for key, value in response.items():
                    pos_additional_fields[cp.pk].append({
                        'answer': data.get('question_form_data', {}).get(key),
                        'question': value.label
                    })

        # Group items of the same variation
        # We do this by list manipulations instead of a GROUP BY query, as
        # Django is unable to join related models in a .values() query
        def keyfunc(pos):
            if isinstance(pos, OrderPosition):
                if pos.addon_to:
                    i = pos.addon_to.positionid
                else:
                    i = pos.positionid
            else:
                if pos.addon_to:
                    i = pos.addon_to.pk
                else:
                    i = pos.pk

            has_attendee_data = pos.item.admission and (
                self.request.event.settings.attendee_names_asked
                or self.request.event.settings.attendee_emails_asked
                or pos_additional_fields.get(pos.pk)
            )
            addon_penalty = 1 if pos.addon_to else 0
            if downloads or pos.pk in has_addons or pos.addon_to:
                return i, addon_penalty, pos.pk, 0, 0, 0, 0, (pos.subevent_id or 0)
            if answers and (has_attendee_data or pos.item.questions.all()):
                return i, addon_penalty, pos.pk, 0, 0, 0, 0, (pos.subevent_id or 0)

            return (
                0, addon_penalty, 0, pos.item_id, pos.variation_id, pos.price, (pos.voucher_id or 0),
                (pos.subevent_id or 0)
            )

        positions = []
        for k, g in groupby(sorted(lcp, key=keyfunc), key=keyfunc):
            g = list(g)
            group = g[0]
            group.count = len(g)
            group.total = group.count * group.price
            group.net_total = group.count * group.net_price
            group.has_questions = answers and k[0] != ""
            group.tax_rule = group.item.tax_rule
            if answers:
                group.cache_answers()
                group.additional_answers = pos_additional_fields.get(group.pk)
            positions.append(group)

        total = sum(p.total for p in positions)
        net_total = sum(p.net_total for p in positions)
        tax_total = sum(p.total - p.net_total for p in positions)

        if order:
            fees = order.fees.all()
        else:
            iapk = self.cart_session.get('invoice_address')
            ia = None
            if iapk:
                try:
                    ia = InvoiceAddress.objects.get(pk=iapk, order__isnull=True)
                except InvoiceAddress.DoesNotExist:
                    pass

            fees = get_fees(self.request.event, self.request, total, ia, self.cart_session.get('payment'))

        total += sum([f.value for f in fees])
        net_total += sum([f.net_value for f in fees])
        tax_total += sum([f.tax_value for f in fees])

        try:
            first_expiry = min(p.expires for p in positions) if positions else now()
            minutes_left = max(first_expiry - now(), timedelta()).seconds // 60
        except AttributeError:
            first_expiry = None
            minutes_left = None

        return {
            'positions': positions,
            'raw': cartpos,
            'total': total,
            'net_total': net_total,
            'tax_total': tax_total,
            'fees': fees,
            'answers': answers,
            'minutes_left': minutes_left,
            'first_expiry': first_expiry,
        }


def get_cart(request):
    from pretix.presale.views.cart import get_or_create_cart_id

    if not hasattr(request, '_cart_cache'):
        request._cart_cache = CartPosition.objects.filter(
            cart_id=get_or_create_cart_id(request), event=request.event
        ).order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation', 'subevent', 'subevent__event', 'subevent__event__organizer',
            'item__tax_rule'
        ).prefetch_related(
            'item__questions', 'answers'
        )
    return request._cart_cache


def get_cart_total(request):
    from pretix.presale.views.cart import get_or_create_cart_id

    if not hasattr(request, '_cart_total_cache'):
        if hasattr(request, '_cart_cache'):
            request._cart_total_cache = sum(i.price for i in request._cart_cache)
        else:
            request._cart_total_cache = CartPosition.objects.filter(
                cart_id=get_or_create_cart_id(request), event=request.event
            ).aggregate(sum=Sum('price'))['sum'] or 0
    return request._cart_total_cache


class EventViewMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['event'] = self.request.event
        return context


class OrganizerViewMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['organizer'] = self.request.organizer
        return context
