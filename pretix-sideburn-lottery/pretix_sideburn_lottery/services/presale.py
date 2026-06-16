from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils.formats import date_format
from django.utils.translation import gettext as _


def get_lottery_date_display(event, item_id):
    """
    Return a localized date string for a scheduled lottery, or None if not set.
    """
    raw = event.settings.get(f"lottery_date_for_item_{item_id}")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(event.settings.timezone))
    else:
        dt = dt.astimezone(ZoneInfo(event.settings.timezone))
    return date_format(dt, "DATE_FORMAT")


def get_sold_out_label(event, item_id):
    lottery_date = get_lottery_date_display(event, item_id)
    if lottery_date:
        return _("Ticket lottery held on %(date)s") % {"date": lottery_date}
    return _("These tickets will be assigned by lottery")
