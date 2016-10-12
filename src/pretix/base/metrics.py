from django.conf import settings

if settings.HAS_REDIS:
    import django_redis

REDIS_KEY_PREFIX = "pretix_metrics_"

redis = django_redis.get_redis_connection("redis")


class MetricsError(Exception):
    pass


class Metric(object):
    """
    Base Metrics Object
    """

    def __init__(self, name, helpstring, labelnames=None):
        self.name = name
        self.helpstring = helpstring
        self.labelnames = labelnames or []

    def __repr__(self):
        return self.name + "{" + ",".join(self.labelnames) + "}"

    def _check_label_consistency(self, labelset):
        """
        Checks if the given labelset provides exactly the labels that are required.
        """

        # test if every required label is provided
        for labelname in self.labelnames:
            if labelname not in labelset:
                raise MetricsError("Label {0} not specified.".format(labelname))

        # now test if no further labels are required
        if len(labelset) != len(self.labelnames):
            s1 = set(labelset)
            s2 = set(labelnames)
            diff = s1.difference(s2)
            raise MetricsError("Unknown labels used: {}".format(", ".join(diff)))

    def _construct_metric_identifier(self, metricname, labelset=None):
        """
        Constructs the scrapable metricname usable in the output format.
        """
        if not labelset:
            return metricname
        else:
            labels = []
            for labelname in self.labelnames:
                labels.append('{}="{}",'.format(labelname, labelset[labelname]))

            return metricname + "{" + ",".join(labels) + "}"

    def _inc_in_redis(self, key, amount):
        """
        Increments given key in Redis.
        """
        rkey = REDIS_KEY_PREFIX + key
        redis.incrbyfloat(rkey, amount)

    def _set_in_redis(self, key, value):
        """
        Sets given key in Redis.
        """
        rkey = REDIS_KEY_PREFIX + key
        redis.set(rkey, value)


class Counter(Metric):
    """
    Counter Metric Object
    Counters can only be increased, they can neither be set to a specific value
    nor decreased.
    """

    def inc(self, amount=1, **kwargs):
        """
        Increments Counter by given amount for the labelset specified in kwargs.
        """
        if amount < 0:
            raise MetricsError("Counter cannot be increased by negative values.")

        self._check_label_consistency(kwargs)

        fullmetric = self._construct_metric_identifier(self.name, kwargs)
        self._inc_in_redis(fullmetric, amount)


class Gauge(Metric):
    """
    Gauge Metric Object
    Gauges can be set to a specific value, increased and decreased.
    """

    def set(self, value=1, **kwargs):
        """
        Sets Gauge to a specific value for the labelset specified in kwargs.
        """
        self._check_label_consistency(kwargs)

        fullmetric = self._construct_metric_identifier(self.name, kwargs)
        self._set_in_redis(fullmetric, value)

    def inc(self, amount=1, **kwargs):
        """
        Increments Gauge by given amount for the labelset specified in kwargs.
        """
        if amount < 0:
            raise MetricsError("Amount must be greater than zero. Otherwise use dec().")

        self._check_label_consistency(kwargs)

        fullmetric = self._construct_metric_identifier(self.name, kwargs)
        self._inc_in_redis(fullmetric, amount)

    def dec(self, amount=1, **kwargs):
        """
        Decrements Gauge by given amount for the labelset specified in kwargs.
        """
        if amount < 0:
            raise MetricsError("Amount must be greater than zero. Otherwise use inc().")

        self._check_label_consistency(self.labelnames, kwargs)

        fullmetric = self._construct_metric_identifier(self.name, kwargs)
        self._inc_in_redis(fullmetric, amount * -1)


def metrics_textformat():
    """
    Produces the scrapable textformat to be presented to the monitoring system
    """
    output = []

    for key in r.scan_iter(match=REDIS_KEY_PREFIX + "*"):
        dkey = key.decode("utf-8")
        _, _, output_key = dkey.split("_", 2)
        value = float(r.get(dkey).decode("utf-8"))

        output.append(output_key + " " + str(value))

    return "\n".join(output)


if not settings.HAS_REDIS:
    # noop everything
    class Counter(object):
        def inc(): pass
    class Gauge(object):
        def inc(): pass
        def dec(): pass
    def metrics_textformat(): pass


"""
Provided metrics
"""
http_requests_total = Counter("http_requests_total", "Total number of HTTP requests made.", ["code", "handler", "method"])
# usage: http_requests_total.inc(code="200", handler="/foo", method="GET")
