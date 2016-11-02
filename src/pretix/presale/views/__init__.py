from datetime import timedelta
from decimal import Decimal
from itertools import groupby

from django.utils.functional import cached_property
from django.utils.timezone import now

from pretix.base.models import CartPosition
from pretix.base.signals import register_payment_providers


class CartMixin:
    @cached_property
    def positions(self):
        """
        A list of this users cart position
        """
        return list(CartPosition.objects.filter(
            cart_id=self.request.session.session_key, event=self.request.event
        ).order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            'item__questions', 'answers'
        ))

    def get_cart(self, answers=False, queryset=None, payment_fee=None, payment_fee_tax_rate=None, downloads=False):
        queryset = queryset or CartPosition.objects.filter(
            cart_id=self.request.session.session_key, event=self.request.event
        )

        prefetch = []
        if answers:
            prefetch.append('item__questions')
            prefetch.append('answers')

        cartpos = queryset.order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            *prefetch
        )

        # Group items of the same variation
        # We do this by list manipulations instead of a GROUP BY query, as
        # Django is unable to join related models in a .values() query
        def keyfunc(pos):
            if downloads:
                return pos.id, 0, 0, 0, 0
            if answers and ((pos.item.admission and self.request.event.settings.attendee_names_asked)
                            or pos.item.questions.all()):
                return pos.id, 0, 0, 0, 0
            return 0, pos.item_id, pos.variation_id, pos.price, (pos.voucher_id or 0)

        positions = []
        for k, g in groupby(sorted(list(cartpos), key=keyfunc), key=keyfunc):
            g = list(g)
            group = g[0]
            group.count = len(g)
            group.total = group.count * group.price
            group.has_questions = answers and k[0] != ""
            if answers:
                group.cache_answers()
            positions.append(group)

        total = sum(p.total for p in positions)

        payment_fee = payment_fee if payment_fee is not None else self.get_payment_fee(total)
        payment_fee_tax_rate = payment_fee_tax_rate if payment_fee_tax_rate is not None else self.request.event.settings.tax_rate_default

        try:
            first_expiry = min(p.expires for p in positions) if positions else now()
            minutes_left = max(first_expiry - now(), timedelta()).seconds // 60
        except AttributeError:
            first_expiry = None
            minutes_left = None

        return {
            'positions': positions,
            'raw': cartpos,
            'total': total + payment_fee,
            'payment_fee': payment_fee,
            'payment_fee_tax_rate': payment_fee_tax_rate,
            'answers': answers,
            'minutes_left': minutes_left,
            'first_expiry': first_expiry
        }

    def get_payment_fee(self, total):
        if total == 0:
            return Decimal('0.00')
        payment_fee = 0
        if 'payment' in self.request.session:
            responses = register_payment_providers.send(self.request.event)
            for receiver, response in responses:
                provider = response(self.request.event)
                if provider.identifier == self.request.session['payment']:
                    payment_fee = provider.calculate_fee(total)
        return payment_fee


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
