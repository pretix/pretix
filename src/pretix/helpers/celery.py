from django.conf import settings

THRESHOLD_DOWNGRADE_TO_MID = 50
THRESHOLD_DOWNGRADE_TO_LOW = 250


def get_task_priority(shard, organizer_id):
    """
    This is an attempt to build a simple "fair-use" policy for webhooks and notifications. The problem is that when
    one organizer creates e.g. 20,000 orders through the API, that might schedule 20,000 webhooks and every other
    organizer will need to wait for these webhooks to go through.

    We try to fix that by building three queues: high-prio, mid-prio, and low-prio. Every organizer starts in the
    high-prio queue, and all their tasks are routed immediately. Once an organizer submits more than X jobs of a
    certain type per minute, they get downgraded to the mid-prio queue, and then – if they submit even more – to the
    low-prio queue. That way, if another organizer has "regular usage", they are prioritized over the organizer with
    high load.
    """
    from django_redis import get_redis_connection

    if not settings.HAS_REDIS:
        return settings.PRIORITY_CELERY_HIGH

    # We use redis directly instead of the Django cache API since the Django cache API does not support INCR for
    # nonexistant keys
    rc = get_redis_connection("redis")

    cache_key = f"pretix:task_priority:{shard}:{organizer_id}"

    new_counter = rc.incr(cache_key)
    print("counter", new_counter)
    if new_counter == 1:
        # Make sure counters expire after a while, but only do so when they are newly set, to avoid additional EXPIRE
        # calls to cache.
        rc.expire(cache_key, 60)

    if new_counter >= THRESHOLD_DOWNGRADE_TO_LOW:
        return settings.PRIORITY_CELERY_LOW
    elif new_counter >= THRESHOLD_DOWNGRADE_TO_MID:
        return settings.PRIORITY_CELERY_MID
    else:
        return settings.PRIORITY_CELERY_HIGH
