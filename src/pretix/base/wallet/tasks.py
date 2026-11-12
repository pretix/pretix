from pretix.base.models import Order, OrderPosition
from pretix.base.services.tasks import ProfiledTask
from pretix.celery_app import app

from pretix.base.wallet.platforms import get_platform


@app.task(base=ProfiledTask)
def get_pass(model: str, pk: int, platform_identifier: str, show_disabled: bool):
    if model == "order":
        order = Order.objects.select_related("event").get(id=pk)
        platform = get_platform(order.event, platform_identifier, show_disabled)
        if not platform:
            return
        return platform.generate_order(order)
    elif model == "orderposition":
        position = OrderPosition.objects.select_related("order", "order__event").get(
            id=pk
        )
        platform = get_platform(position.order.event, platform_identifier, show_disabled)
        if not platform:
            return
        return platform.generate(position)
