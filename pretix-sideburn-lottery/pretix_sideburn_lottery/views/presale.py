from zoneinfo import ZoneInfo

from django.utils.timezone import now

from pretix.base.models import WaitingListEntry

from ..services.rank import get_waiting_list_rank


def get_waiting_list_ranks(event, customer_email):
    """
    Get waiting list ranks for a customer.

    Returns a list of product data dictionaries with rank information.
    Each dictionary contains: item_id, item_name, variation_id, variation_name, rank,
    lottery_run, and optionally voucher_code, voucher_expired, and voucher_expired_date.
    """
    entries = WaitingListEntry.objects.filter(
        event=event,
        email__iexact=customer_email,
    ).select_related("item", "variation", "voucher").order_by(
        "item", "variation", "-created", "-pk"
    )

    products_data = []
    seen_products = set()

    for entry in entries:
        product_key = (entry.item_id, entry.variation_id if entry.variation else None)

        if product_key in seen_products:
            continue

        seen_products.add(product_key)

        rank = get_waiting_list_rank(entry)

        voucher_expired = False
        voucher_expired_date = None
        if rank is None and entry.voucher and not entry.voucher.is_active():
            if entry.voucher.valid_until and entry.voucher.valid_until < now():
                voucher_expired = True
                tz = ZoneInfo(event.settings.timezone)
                voucher_expired_date = entry.voucher.valid_until.astimezone(tz)

        if rank is None and not voucher_expired:
            continue

        lottery_date = event.settings.get(f"lottery_date_for_item_{entry.item_id}")
        lottery_run = bool(lottery_date)

        product_data = {
            "item_id": entry.item_id,
            "item_name": str(entry.item),
            "variation_id": entry.variation_id,
            "variation_name": str(entry.variation) if entry.variation else None,
            "rank": rank,
            "lottery_run": lottery_run,
        }

        if rank == 0 and entry.voucher:
            product_data["voucher_code"] = entry.voucher.code

        if voucher_expired:
            product_data["voucher_expired"] = True
            product_data["voucher_expired_date"] = voucher_expired_date

        products_data.append(product_data)

    return products_data
