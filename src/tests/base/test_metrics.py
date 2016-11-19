# pytest

from django.test import override_settings

from pretix.base import metrics


class fake_redis(object):

    def __init__(self):
        self.storage = {}

    def incrbyfloat(self, rkey, amount):
        if rkey in self.storage:
            self.storage[rkey] += amount
        else:
            self.set(rkey, amount)

    def set(self, rkey, value):
        self.storage[rkey] = value

    def get(self, rkey):
        # bytes-conversion here for emulating redis behavior without making incr too hard
        return bytes(self.storage[rkey], encoding='utf-8')


@override_settings(HAS_REDIS=True)
def test_counter(monkeypatch):

    local_fake_redis = fake_redis()

    monkeypatch.setattr(metrics, "redis", local_fake_redis, raising=False)

    # now test
    fullname = metrics.http_requests_total._construct_metric_identifier('http_requests_total', {"code": "200", "handler": "/foo", "method": "GET"})
    metrics.http_requests_total.inc(code="200", handler="/foo", method="GET")
    assert local_fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname] == 1
    metrics.http_requests_total.inc(code="200", handler="/foo", method="GET")
    assert local_fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname] == 2
    metrics.http_requests_total.inc(7, code="200", handler="/foo", method="GET")
    assert local_fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname] == 9
