from django.conf import settings

if settings.HAS_REDIS:
    import django_redis
    redis = django_redis.get_redis_connection("redis")

REDIS_KEY_PREFIX = "pretix_metrics_"


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

    def _check_label_consistency(self, labels):
        """
        Checks if the given labels provides exactly the labels that are required.
        """

        # test if every required label is provided
        for labelname in self.labelnames:
            if labelname not in labels:
                raise ValueError("Label {0} not specified.".format(labelname))

        # now test if no further labels are required
        if len(labels) != len(self.labelnames):
            raise ValueError("Unknown labels used: {}".format(", ".join(set(labels) - set(self.labelnames))))

    def _construct_metric_identifier(self, metricname, labels=None):
        """
        Constructs the scrapable metricname usable in the output format.
        """
        if not labels:
            return metricname
        else:
            named_labels = []
            for labelname in self.labelnames:
                named_labels.append('{}="{}",'.format(labelname, labels[labelname]))

            return metricname + "{" + ",".join(named_labels) + "}"

    def _inc_in_redis(self, key, amount):
        """
        Increments given key in Redis.
        """
        rkey = REDIS_KEY_PREFIX + key
        if settings.HAS_REDIS:
            redis.incrbyfloat(rkey, amount)

    def _set_in_redis(self, key, value):
        """
        Sets given key in Redis.
        """
        rkey = REDIS_KEY_PREFIX + key
        if settings.HAS_REDIS:
            redis.set(rkey, value)


class Counter(Metric):
    """
    Counter Metric Object
    Counters can only be increased, they can neither be set to a specific value
    nor decreased.
    """

    def inc(self, amount=1, **kwargs):
        """
        Increments Counter by given amount for the labels specified in kwargs.
        """
        if amount < 0:
            raise ValueError("Counter cannot be increased by negative values.")

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
        Sets Gauge to a specific value for the labels specified in kwargs.
        """
        self._check_label_consistency(kwargs)

        fullmetric = self._construct_metric_identifier(self.name, kwargs)
        self._set_in_redis(fullmetric, value)

    def inc(self, amount=1, **kwargs):
        """
        Increments Gauge by given amount for the labels specified in kwargs.
        """
        if amount < 0:
            raise ValueError("Amount must be greater than zero. Otherwise use dec().")

        self._check_label_consistency(kwargs)

        fullmetric = self._construct_metric_identifier(self.name, kwargs)
        self._inc_in_redis(fullmetric, amount)

    def dec(self, amount=1, **kwargs):
        """
        Decrements Gauge by given amount for the labels specified in kwargs.
        """
        if amount < 0:
            raise ValueError("Amount must be greater than zero. Otherwise use inc().")

        self._check_label_consistency(kwargs)

        fullmetric = self._construct_metric_identifier(self.name, kwargs)
        self._inc_in_redis(fullmetric, amount * -1)


def metric_values():
    """
    Produces the scrapable textformat to be presented to the monitoring system
    """
    if not settings.HAS_REDIS:
        return ""

    metrics = {}

    for key in redis.scan_iter(match=REDIS_KEY_PREFIX + "*"):
        dkey = key.decode("utf-8")
        _, _, output_key = dkey.split("_", 2)
        value = float(redis.get(dkey).decode("utf-8"))

        metrics[output_key] = value

    return metrics


"""
Provided metrics
"""
http_requests_total = Counter("http_requests_total", "Total number of HTTP requests made.", ["code", "handler", "method"])
# usage: http_requests_total.inc(code="200", handler="/foo", method="GET")
