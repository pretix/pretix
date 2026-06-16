import csv
import io
import random

from django.http import HttpResponse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _


def lottery_results_filename(event_slug, *, revert=False):
    if revert:
        return "{}_lottery_results_REVERTED".format(event_slug)
    return "{}_lottery_results".format(event_slug)


def run_lottery(event, queryset, item_id, *, revert=False):
    """
    Run or revert the waiting-list lottery for a product.

    Shuffles priorities (run) or restores original order (revert), updates
    lottery_date_for_item_{item_id} on the event, and returns a CSV download.

    Returns None if there are no matching waiting-list entries.
    """
    qs = list(queryset.filter(item_id=item_id))
    if not qs:
        return None

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC, delimiter=",")

    qs = sorted(qs, key=lambda o: o.created, reverse=True)
    priority_count = len(qs)
    new_priorities = list(range(1, priority_count + 1))

    if not revert:
        random.shuffle(new_priorities)
    new_priorities_iter = iter(new_priorities)

    for w in qs:
        w.old_priority = w.priority
        w.priority = next(new_priorities_iter)
        w.save(update_fields=["priority"])

    qs = sorted(qs, key=lambda o: o.priority, reverse=True)

    if not revert:
        event.settings.set(f"lottery_date_for_item_{item_id}", now().isoformat())
    else:
        event.settings.delete(f"lottery_date_for_item_{item_id}")

    headers = [
        _("Name"),
        _("E-mail address"),
        _("Phone number"),
        _("Product"),
        _("On list since"),
        _("Status"),
        _("Voucher code"),
        _("Language"),
        _("Priority"),
        "OldPriority",
    ]
    writer.writerow(headers)

    for w in qs:
        if w.item:
            if w.variation:
                prod = "%s – %s" % (str(w.item), str(w.variation))
            else:
                prod = "%s" % str(w.item)
        if w.voucher:
            if w.voucher.redeemed >= w.voucher.max_usages:
                status = _("Voucher redeemed")
            elif not w.voucher.is_active():
                status = _("Voucher expired")
            else:
                status = _("Voucher assigned")
        else:
            status = _("Waiting")

        row = [
            w.name,
            w.email,
            w.phone,
            prod,
            w.created.isoformat(),
            status,
            w.voucher.code if w.voucher else "",
            w.locale,
            str(w.priority),
            str(w.old_priority),
        ]
        if event.has_subevents:
            row.append(str(w.subevent))
        writer.writerow(row)

    response = HttpResponse(output.getvalue().encode("utf-8"), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="{}.csv"'.format(
        lottery_results_filename(event.slug, revert=revert)
    )
    return response
