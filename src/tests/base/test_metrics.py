# pytest

import base64

import pytest
from django.test import override_settings

from pretix.base import metrics
from pretix.base.views import metrics as metricsview


class FakeRedis(object):

    def __init__(self):
        self.storage = {}

    def hincrbyfloat(self, k, rkey, amount):
        if rkey in self.storage:
            self.storage[rkey] += amount
        else:
            self.hset(k, rkey, amount)

    def hset(self, k, rkey, value):
        self.storage[rkey] = value

    def hget(self, k, rkey):
        # bytes-conversion here for emulating redis behavior without making incr too hard
        return bytes(self.storage[rkey], encoding='utf-8')

    def pipeline(self):
        return self

    def execute(self):
        pass


@override_settings(HAS_REDIS=True)
def test_counter(monkeypatch):

    fake_redis = FakeRedis()

    monkeypatch.setattr(metrics, "redis", fake_redis, raising=False)
    pretix_view_requests_total = metrics.Counter("pretix_view_requests_total", "Total number of HTTP requests made.",
                                                 ["status_code", "method", "url_name"])

    # now test
    fullname_get = pretix_view_requests_total._construct_metric_identifier(
        'pretix_view_requests_total', {"status_code": "200", "url_name": "foo", "method": "GET"}
    )
    fullname_post = pretix_view_requests_total._construct_metric_identifier(
        'pretix_view_requests_total', {"status_code": "200", "url_name": "foo", "method": "POST"}
    )
    pretix_view_requests_total.inc(status_code="200", url_name="foo", method="GET")
    assert fake_redis.storage[fullname_get] == 1
    pretix_view_requests_total.inc(status_code="200", url_name="foo", method="GET")
    assert fake_redis.storage[fullname_get] == 2
    pretix_view_requests_total.inc(7, status_code="200", url_name="foo", method="GET")
    assert fake_redis.storage[fullname_get] == 9
    pretix_view_requests_total.inc(7, status_code="200", url_name="foo", method="POST")
    assert fake_redis.storage[fullname_get] == 9
    assert fake_redis.storage[fullname_post] == 7

    with pytest.raises(ValueError):
        pretix_view_requests_total.inc(-4, status_code="200", url_name="foo", method="POST")

    with pytest.raises(ValueError):
        pretix_view_requests_total.inc(-4, status_code="200", url_name="foo", method="POST", too="much")

    # test dimensionless counters
    dimless_counter = metrics.Counter("dimless_counter", "this is a helpstring")
    fullname_dimless = dimless_counter._construct_metric_identifier('dimless_counter')
    dimless_counter.inc(20)
    assert fake_redis.storage[fullname_dimless] == 20


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
    assert fake_redis.storage[fullname_one] == 1
    test_gauge.inc(7, dimension="one")
    assert fake_redis.storage[fullname_one] == 8
    test_gauge.dec(2, dimension="one")
    assert fake_redis.storage[fullname_one] == 6
    test_gauge.set(3, dimension="two")
    assert fake_redis.storage[fullname_one] == 6
    assert fake_redis.storage[fullname_two] == 3
    test_gauge.set(4, dimension="two")
    assert fake_redis.storage[fullname_one] == 6
    assert fake_redis.storage[fullname_two] == 4
    test_gauge.dec(7, dimension="three")
    assert fake_redis.storage[fullname_one] == 6
    assert fake_redis.storage[fullname_two] == 4
    assert fake_redis.storage[fullname_three] == -7
    test_gauge.inc(14, dimension="three")
    assert fake_redis.storage[fullname_one] == 6
    assert fake_redis.storage[fullname_two] == 4
    assert fake_redis.storage[fullname_three] == 7
    test_gauge.set(17, dimension="three")
    assert fake_redis.storage[fullname_one] == 6
    assert fake_redis.storage[fullname_two] == 4
    assert fake_redis.storage[fullname_three] == 17

    with pytest.raises(ValueError):
        test_gauge.inc(-17, dimension="three")

    with pytest.raises(ValueError):
        test_gauge.dec(-17, dimension="three")

    with pytest.raises(ValueError):
        test_gauge.set(7, unknown_label="foo")

    with pytest.raises(ValueError):
        test_gauge.set(7, dimension="one", too="much")

    # test dimensionless gauges
    dimless_gauge = metrics.Gauge("dimless_gauge", "this is a helpstring")
    fullname_dimless = dimless_gauge._construct_metric_identifier('dimless_gauge')
    dimless_gauge.set(20)
    assert fake_redis.storage[fullname_dimless] == 20


@override_settings(HAS_REDIS=True)
def test_histogram(monkeypatch):

    fake_redis = FakeRedis()

    monkeypatch.setattr(metrics, "redis", fake_redis, raising=False)

    test_hist = metrics.Histogram("my_histogram", "this is a helpstring", ["dimension"])

    # now test
    test_hist.observe(3.0, dimension="one")
    assert fake_redis.storage['my_histogram_count{dimension="one"}'] == 1
    assert fake_redis.storage['my_histogram_sum{dimension="one"}'] == 3.0
    assert fake_redis.storage['my_histogram_bucket{dimension="one",le="5.0"}'] == 1
    assert fake_redis.storage['my_histogram_bucket{dimension="one",le="10.0"}'] == 1
    assert fake_redis.storage['my_histogram_bucket{dimension="one",le="+Inf"}'] == 1
    test_hist.observe(3.0, dimension="one")
    assert fake_redis.storage['my_histogram_count{dimension="one"}'] == 2
    assert fake_redis.storage['my_histogram_sum{dimension="one"}'] == 6.0
    assert fake_redis.storage['my_histogram_bucket{dimension="one",le="5.0"}'] == 2
    test_hist.observe(0.9, dimension="one")
    assert fake_redis.storage['my_histogram_count{dimension="one"}'] == 3
    assert fake_redis.storage['my_histogram_sum{dimension="one"}'] == 6.9
    assert fake_redis.storage['my_histogram_bucket{dimension="one",le="5.0"}'] == 3
    assert fake_redis.storage['my_histogram_bucket{dimension="one",le="1.0"}'] == 1
    test_hist.observe(0.9, dimension="two")
    assert fake_redis.storage['my_histogram_count{dimension="one"}'] == 3
    assert fake_redis.storage['my_histogram_count{dimension="two"}'] == 1
    assert fake_redis.storage['my_histogram_sum{dimension="one"}'] == 6.9
    assert fake_redis.storage['my_histogram_sum{dimension="two"}'] == 0.9
    assert fake_redis.storage['my_histogram_bucket{dimension="one",le="5.0"}'] == 3
    assert fake_redis.storage['my_histogram_bucket{dimension="one",le="1.0"}'] == 1
    assert fake_redis.storage['my_histogram_bucket{dimension="two",le="1.0"}'] == 1


@pytest.mark.django_db
@override_settings(HAS_REDIS=True, METRICS_USER="foo", METRICS_PASSPHRASE="bar")
def test_metrics_view(monkeypatch, client):

    fake_redis = FakeRedis()
    monkeypatch.setattr(metricsview.metrics, "redis", fake_redis, raising=False)

    counter_value = 3
    pretix_view_requests_total = metrics.Counter("pretix_view_requests_total", "Total number of HTTP requests made.",
                                                 ["status_code", "method", "url_name"])
    fullname = pretix_view_requests_total._construct_metric_identifier(
        'http_requests_total',
        {"status_code": "200", "url_name": "foo", "method": "GET"}
    )
    pretix_view_requests_total.inc(counter_value, status_code="200", url_name="foo", method="GET")

    # test unauthorized-page
    assert "You are not authorized" in client.get('/metrics').content.decode('utf-8')
    assert "{} {}".format(fullname, counter_value) not in client.get('/metrics')

    # test metrics-view
    basic_auth = {"HTTP_AUTHORIZATION": base64.b64encode(bytes("foo:bar", "utf-8"))}
    assert "{} {}".format(fullname, counter_value) not in client.get("/metrics", headers=basic_auth)


@pytest.mark.django_db
@override_settings(HAS_REDIS=True, METRICS_USER="foo", METRICS_PASSPHRASE="bar")
def test_do_not_break_append_slash(monkeypatch, client):
    r = client.get('/control')
    assert r.status_code == 301
    assert r['Location'] == '/control/'
