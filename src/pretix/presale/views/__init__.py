from itertools import groupby
from datetime import timedelta
from django.contrib.auth.views import redirect_to_login
from django.core.urlresolvers import reverse

from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.timezone import now

from pretix.base.models import CartPosition
from pretix.base.signals import register_payment_providers


class EventLoginRequiredMixin:

    @classmethod
    def as_view(cls, **initkwargs):
        view = super(EventLoginRequiredMixin, cls).as_view(**initkwargs)

        def decorator(view_func):
            def _wrapped_view(request, *args, **kwargs):
                if request.user.is_authenticated() and \
                        (request.user.event is None or request.user.event == request.event):
                    return view_func(request, *args, **kwargs)
                path = request.path
                return redirect_to_login(
                    path, reverse('presale:event.checkout.login', kwargs={
                        'organizer': request.event.organizer.slug,
                        'event': request.event.slug,
                    }), 'next'
                )
            return _wrapped_view
        return decorator(view)


class CartDisplayMixin:

    @cached_property
    def cartpos(self):
        """
        A list of this users cart position
        """
        return list(CartPosition.objects.current.filter(
            Q(user=self.request.user) & Q(event=self.request.event)
        ).order_by(
            'item', 'variation'
        ).select_related(
            'item', 'variation'
        ).prefetch_related(
            'variation__values', 'variation__values__prop',
            'item__questions', 'answers'
        ))

    def get_cart(self, answers=False, queryset=None, payment_fee=None):
        queryset = queryset or CartPosition.objects.current.filter(
            Q(user=self.request.user) & Q(event=self.request.event)
        )

        prefetch = ['variation__values', 'variation__values__prop']
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
            if answers and ((pos.item.admission and self.request.event.settings.attendee_names_asked == 'True')
                            or pos.item.questions.all()):
                return pos.id, "", "", ""
            return "", pos.item_id, pos.variation_id, pos.price

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

        payment_fee = payment_fee or self.get_payment_fee(total)

        try:
            minutes_left = max(min(p.expires for p in positions) - now(), timedelta()).seconds // 60 if positions else 0
        except AttributeError:
            minutes_left = None

        return {
            'positions': positions,
            'raw': cartpos,
            'total': total + payment_fee,
            'payment_fee': payment_fee,
            'answers': answers,
            'minutes_left': minutes_left,
        }

    def get_payment_fee(self, total):
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
