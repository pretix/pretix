# pytest

from django.test import override_settings

from pretix.base import metrics
from pretix.base.views import metrics as metricsview


class FakeRedis(object):

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

    fake_redis = FakeRedis()

    monkeypatch.setattr(metrics, "redis", fake_redis, raising=False)

    # now test
    fullname_GET  = metrics.http_requests_total._construct_metric_identifier('http_requests_total', {"code": "200", "handler": "/foo", "method": "GET"})
    fullname_POST = metrics.http_requests_total._construct_metric_identifier('http_requests_total', {"code": "200", "handler": "/foo", "method": "POST"})
    metrics.http_requests_total.inc(code="200", handler="/foo", method="GET")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_GET] == 1
    metrics.http_requests_total.inc(code="200", handler="/foo", method="GET")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_GET] == 2
    metrics.http_requests_total.inc(7, code="200", handler="/foo", method="GET")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_GET] == 9
    metrics.http_requests_total.inc(7, code="200", handler="/foo", method="POST")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_GET] == 9
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_POST] == 7
