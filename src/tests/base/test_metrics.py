# pytest

import base64

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
    fullname_GET = metrics.http_requests_total._construct_metric_identifier('http_requests_total', {"code": "200", "handler": "/foo", "method": "GET"})
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


@override_settings(HAS_REDIS=True)
def test_gauge(monkeypatch):

    fake_redis = FakeRedis()

    monkeypatch.setattr(metrics, "redis", fake_redis, raising=False)

    test_gauge = metrics.Gauge("my_gauge", "this is a helpstring", ["dimension"])

    # now test
    fullname_one = test_gauge._construct_metric_identifier('my_gauge', {"dimension": "one"})
    fullname_two = test_gauge._construct_metric_identifier('my_gauge', {"dimension": "two"})
    fullname_three = test_gauge._construct_metric_identifier('my_gauge', {"dimension": "three"})

    test_gauge.inc(dimension="one")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_one] == 1
    test_gauge.inc(7, dimension="one")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_one] == 8
    test_gauge.dec(2, dimension="one")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_one] == 6
    test_gauge.set(3, dimension="two")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_one] == 6
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_two] == 3
    test_gauge.set(4, dimension="two")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_one] == 6
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_two] == 4
    test_gauge.dec(7, dimension="three")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_one] == 6
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_two] == 4
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_three] == -7
    test_gauge.inc(14, dimension="three")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_one] == 6
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_two] == 4
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_three] == 7
    test_gauge.set(17, dimension="three")
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_one] == 6
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_two] == 4
    assert fake_redis.storage[metrics.REDIS_KEY_PREFIX + fullname_three] == 17


@override_settings(HAS_REDIS=True, METRICS_USER="foo", METRICS_PASSPHRASE="bar")
def test_metrics_view(monkeypatch, client):

    fake_redis = FakeRedis()
    monkeypatch.setattr(metricsview.metrics, "redis", fake_redis, raising=False)

    counter_value = 3
    fullname = metrics.http_requests_total._construct_metric_identifier('http_requests_total', {"code": "200", "handler": "/foo", "method": "GET"})
    metricsview.metrics.http_requests_total.inc(counter_value, code="200", handler="/foo", method="GET")

    # test unauthorized-page
    assert "You are not authorized" in metricsview.serve_metrics(None).content.decode('utf-8')
    assert "You are not authorized" in client.get('/metrics').content.decode('utf-8')
    assert "{} {}".format(fullname, counter_value) not in client.get('/metrics')

    # test metrics-view
    basic_auth = {"HTTP_AUTHORIZATION": base64.b64encode(bytes("foo:bar", "utf-8"))}
    assert "{} {}".format(fullname, counter_value) not in client.get("/metrics", headers=basic_auth)
