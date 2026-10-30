

from django.http import Http404
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    View,
)
from pretix.base.models.orders import OrderPosition
from pretix.base.services.orders import OrderError
from pretix.base.views.tasks import AsyncAction

from django.db.models import Q

from django.http import (
    Http404,
)
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import View

from pretix.base.models import (
    OrderPosition,
)
from pretix.base.services.orders import (
    OrderError,
)
from pretix.base.views.tasks import AsyncAction
from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.views import (
    EventViewMixin,
)
from pretix.presale.views.order import OrderDetailMixin, OrderPositionDetailMixin

from .control import OrderDownloadMixin

class PresaleOrderDownloadMixin(OrderDownloadMixin):
    known_errortypes = ['OrderError']

    def post(self, request, *args, **kwargs):
        # TODO: check if available if is_available is implemented (or check in super.platform?)
        if not self.platform:
            return self.error(OrderError(_('You requested an invalid ticket output type.')))
        if not self.order or ('position' in kwargs and not self.order_position):
            raise Http404(_('Unknown order code or not authorized to access this order.'))
        positions = list(self.order.positions_with_tickets)
        if not self.order.ticket_download_available or not positions:
            return self.error(OrderError(_('Ticket download is not (yet) enabled for this order.')))
        if 'position' in kwargs and self.order_position not in positions:
            return self.error(OrderError(_('Ticket download is not enabled for this product.')))

        if (
            self.request.event.settings.ticket_download_require_validated_email and
            self.order.sales_channel.type == 'web' and
            not self.order.email_known_to_work
        ):
            return self.error(OrderError(_('Please click the link we sent you via email to download your tickets.')))

        if "position" in kwargs:
            if not self.order_position.generate_ticket:
                return self.error(_("Ticket download is not enabled for this product."))
            return self.do(
                "orderposition", self.order_position.pk, self.platform.identifier
            )
        else:
            return self.do("order", self.order.pk, self.platform.identifier)


@method_decorator(xframe_options_exempt, 'dispatch')
class PresaleWalletGetPass(PresaleOrderDownloadMixin, EventViewMixin, OrderDetailMixin, AsyncAction, View):
    def get_error_url(self):
        return self.get_order_url()

    def get_self_url(self):
        return eventreverse(self.request.event,
                            'presale:event.order.download' if 'position' in self.kwargs
                            else 'presale:event.order.download.combined',
                            kwargs=self.kwargs)

    @cached_property
    def order_position(self):
        try:
            return self.order.positions.get(pk=self.kwargs.get('position'))
        except OrderPosition.DoesNotExist:
            return None

@method_decorator(xframe_options_exempt, 'dispatch')
class PresaleWalletGetPassPosition(PresaleOrderDownloadMixin, EventViewMixin, OrderPositionDetailMixin, AsyncAction, View):
    def get_error_url(self):
        return self.get_position_url()

    def get_self_url(self):
        return eventreverse(self.request.event,
                            'presale:event.order.position.download',
                            kwargs=self.kwargs)

    @cached_property
    def order_position(self):
        try:
            return self.order.positions.get(
                Q(pk=self.kwargs.get('pid')) & Q(
                    Q(pk=self.position.pk) | Q(addon_to__id=self.position.pk)
                )
            )
        except OrderPosition.DoesNotExist:
            return None