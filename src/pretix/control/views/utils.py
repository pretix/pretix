from pretix.base.services.quotas import QuotaAvailability


def prepare_quotas_for_boxes(quotas):
    qa = QuotaAvailability(early_out=False)
    for q in quotas:
        qa.queue(q)
    qa.compute()

    for q in quotas:
        q.cached_avail = qa.results[q]
        q.cached_availability_paid_orders = qa.count_paid_orders.get(q, 0)
        if q.size is not None:
            other_blocked = q.size - q.cached_availability_paid_orders - q.cached_avail[1]
            q.percent_paid = min(
                100,
                round(q.cached_availability_paid_orders / q.size * 100) if q.size > 0 else 100
            )
            q.percent_other = min(
                100,
                round(other_blocked / q.size * 100) if q.size > 0 else 100
            )
