def refresh_order(order):
    if not order.payment_provider.startswith('stripe_'):
        raise ValueError("Not a stripe payment")

    prov = order.event.get_payment_providers()[order.payment_provider]
    prov._init_api()
