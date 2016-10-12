import redis

ns_prefix = "pretix_metrics_"

r = redis.Redis(host=redishost, port=redisport)


class MetricsError(Exception):
    def __init__(self, msg):
        self.msg = msg


class Metric(object):
    """
    Base Metrics Object
    """

    def __init__(self, name, helpstring, labelnames=[]):
        self.name = name
        self.help = helpstring
        self.labelnames = labelnames


    def __repr__(self):
        return self.name + "{" + ",".join(self.labelnames) + "}"


    def __str__(self):
        return self.__repr__()


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
            raise MetricsError("Unknown label used.")


    def _construct_metric_identifier(self, metricname, labelset=None):
        """
        Constructs the scrapable metricname usable in the output format.
        """
        if not labelset:
            return metricname
        else:
            metricname += "{"
            for labelname in self.labelnames:
                metricname += '{0}="{1}",'.format(labelname, labelset[labelname])

            return metricname[:-1] + "}"


    def _inc_in_redis(self, key, amount):
        """
        Increments given key in Redis.
        """
        rkey = ns_prefix + key  # effective key for redis
        r.incrby(rkey, amount)


    def _set_in_redis(self, key, value):
        """
        Sets given key in Redis.
        """
        rkey = ns_prefix + key  # effective key for redis
        r.set(rkey, value)


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
            raise MetricsError("Counter cannot be decreased.")

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

        fullmetric = self._construct_metric_identifier(name, kwargs)
        self._inc_in_redis(fullmetric, -1*amount)



def metrics_scrapable_textformat():
    """
    Produces the scrapable textformat to be presented to the monitoring system
    """
    output = []

    for key in r.scan_iter(match=ns_prefix + "*"):
        dkey = key.decode("utf-8")
        _, _, output_key = dkey.split("_", 2)
        value = float(r.get(dkey).decode("utf-8"))

        output.append(output_key + " " + str(value))

    return "\n".join(output)



"""
Provided metrics
"""
http_requests_total = Counter("http_requests_total", "Total number of HTTP requests made.", ["code", "handler", "method"])
# usage: http_requests_total.inc(code="200", handler="/foo", method="GET")
