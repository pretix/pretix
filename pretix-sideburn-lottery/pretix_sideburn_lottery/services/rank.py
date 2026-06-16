from django.db.models import F, Q
from django.utils.timezone import now

from pretix.base.models import WaitingListEntry


def get_waiting_list_rank(entry):
    """
    Calculate the rank/position of a waiting list entry.

    Returns:
        - 0 if this entry has a valid, unredeemed voucher (waiting for redemption)
        - None if this entry has an expired or fully redeemed voucher
        - int (1-based rank) if this entry has no voucher - position in waiting list
    """
    # Check if entry has a voucher
    if entry.voucher:
        # Check if voucher is expired
        if not entry.voucher.is_active():
            return None
        # Voucher is valid and not fully redeemed - waiting for redemption
        return 0

    # No voucher - calculate rank in waiting list
    # Filter by same event, item, variation, and subevent
    qs = WaitingListEntry.objects.filter(
        event=entry.event,
        item=entry.item,
        variation=entry.variation,
        subevent=entry.subevent,
    )

    # Include entries that are active:
    # - No voucher (voucher__isnull=True), OR
    # - Valid voucher (not expired and not fully redeemed)
    valid_voucher_q = Q(voucher__valid_until__isnull=True) | Q(
        voucher__valid_until__gte=now()
    )
    unredeemed_q = Q(voucher__redeemed__lt=F("voucher__max_usages"))

    qs = qs.filter(
        Q(voucher__isnull=True)
        | (Q(voucher__isnull=False) & valid_voucher_q & unredeemed_q)
    )

    # Count entries that come before this entry in the ordered queryset
    # Ordering is: -priority (desc), created (asc), pk (asc)
    # So entries before this one have:
    # - Higher priority (priority > entry.priority), OR
    # - Same priority and earlier created (priority == entry.priority AND created < entry.created), OR
    # - Same priority, same created, lower pk (priority == entry.priority AND created == entry.created AND pk < entry.pk)
    before_q = (
        Q(priority__gt=entry.priority)
        | Q(priority=entry.priority, created__lt=entry.created)
        | Q(
            priority=entry.priority,
            created=entry.created,
            pk__lt=entry.pk,
        )
    )

    rank = qs.filter(before_q).count() + 1
    return rank
