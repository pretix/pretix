import math

from django.conf import settings

if settings.HAS_REDIS:
    import django_redis
    redis = django_redis.get_redis_connection("redis")

REDIS_KEY = "pretix_metrics"
_INF = float("inf")
_MINUS_INF = float("-inf")


def _float_to_go_string(d):
    # inspired by https://github.com/prometheus/client_python/blob/master/prometheus_client/core.py
    if d == _INF:
        return '+Inf'
    elif d == _MINUS_INF:
        return '-Inf'
    elif math.isnan(d):
        return 'NaN'
    else:
        return repr(float(d))


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

    def _construct_metric_identifier(self, metricname, labels=None, labelnames=None):
        """
        Constructs the scrapable metricname usable in the output format.
        """
        if not labels:
            return metricname
        else:
            named_labels = []
            for labelname in (labelnames or self.labelnames):
                named_labels.append('{}="{}"'.format(labelname, labels[labelname]))

            return metricname + "{" + ",".join(named_labels) + "}"

    def _inc_in_redis(self, key, amount):
        """
        Increments given key in Redis.
        """
        if settings.HAS_REDIS:
            redis.hincrbyfloat(REDIS_KEY, key, amount)

    def _set_in_redis(self, key, value):
        """
        Sets given key in Redis.
        """
        if settings.HAS_REDIS:
            redis.hset(REDIS_KEY, key, value)


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


class Histogram(Metric):
    """
    Histogram Metric Object
    """

    def __init__(self, name, helpstring, labelnames=None,
                 buckets=(.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, 30.0, _INF)):
        if list(buckets) != sorted(buckets):
            # This is probably an error on the part of the user,
            # so raise rather than sorting for them.
            raise ValueError('Buckets not in sorted order')

        if buckets and buckets[-1] != _INF:
            buckets.append(_INF)

        if len(buckets) < 2:
            raise ValueError('Must have at least two buckets')

        self.buckets = buckets
        super().__init__(name, helpstring, labelnames)

    def observe(self, amount, **kwargs):
        """
        Stores a value in the histogram for the labels specified in kwargs.
        """
        if amount < 0:
            raise ValueError("Amount must be greater than zero. Otherwise use inc().")

        self._check_label_consistency(kwargs)

        countmetric = self._construct_metric_identifier(self.name + '_count', kwargs)
        self._inc_in_redis(countmetric, 1)

        summetric = self._construct_metric_identifier(self.name + '_sum', kwargs)
        self._inc_in_redis(summetric, amount)

        for i, bound in enumerate(self.buckets):
            if amount <= bound:
                kwargs_le = dict(kwargs.items())
                kwargs_le['le'] = _float_to_go_string(bound)
                bmetric = self._construct_metric_identifier(self.name + '_bucket', kwargs_le,
                                                            labelnames=self.labelnames + ["le"])
                self._inc_in_redis(bmetric, 1)
                break


def metric_values():
    """
    Produces the scrapable textformat to be presented to the monitoring system
    """
    if not settings.HAS_REDIS:
        return ""

    metrics = {}

    for key, value in redis.hscan_iter(REDIS_KEY):
        dkey = key.decode("utf-8")
        _, _, output_key = dkey.split("_", 2)
        value = float(value.decode("utf-8"))

        metrics[output_key] = value

    return metrics


"""
Provided metrics
"""
http_view_requests = Counter("http_view_requests", "Total number of HTTP requests made.",
                             ["status_code", "method", "url_name"])
http_view_times = Histogram("http_view_times", "Return time of views.",
                            ["status_code", "method", "url_name"])
celery_task_runs = Counter("celery_task_runs", "Total calls to a celery task",
                           ["task_name", "status"])
celery_task_times = Histogram("celery_task_times", "Call time of a celery task",
                              ["task_name"])
