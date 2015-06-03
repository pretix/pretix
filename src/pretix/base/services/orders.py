from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils.timezone import now
from pretix.base.models import Order, Quota
from django.utils.translation import ugettext_lazy as _


def mark_order_paid(order, provider=None, info=None, date=None, manual=None, force=False):
    """
    Marks an order as paid. This clones the order object, sets the payment provider,
    info and date and returns the cloned order object.

    :param provider: The payment provider that marked this as paid
    :type provider: str
    :param info: The information to store in order.payment_info
    :type info: str
    :param date: The date the payment was received (if you pass ``None``, the current
                 time will be used).
    :type date: datetime
    :param force: Whether this payment should be marked as paid even if no remaining
                  quota is available (default: ``False``).
    :type force: boolean
    :raises Quota.QuotaExceededException: if the quota is exceeded and ``force`` is ``False``
    """
    can_be_paid, quotas_locked = order._can_be_paid(keep_locked=True)
    if not force and can_be_paid is not True:
        raise Quota.QuotaExceededException(can_be_paid)
    order = order.clone()
    order.payment_provider = provider or order.payment_provider
    order.payment_info = info or order.payment_info
    order.payment_date = date or now()
    if manual is not None:
        order.payment_manual = manual
    order.status = Order.STATUS_PAID
    order.save()

    if quotas_locked:
        for quota in quotas_locked:
            quota.release()

    from pretix.base.services.mail import mail

    mail(
        order.user, _('Payment received for your order: %(code)s') % {'code': order.code},
        'pretixpresale/email/order_paid.txt',
        {
            'user': order.user,
            'order': order,
            'event': order.event,
            'url': settings.SITE_URL + reverse('presale:event.order', kwargs={
                'event': order.event.slug,
                'organizer': order.event.organizer.slug,
                'order': order.code
            }),
            'downloads': order.event.settings.get('ticket_download', as_type=bool)
        },
        order.event
    )
    return order
