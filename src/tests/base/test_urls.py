from importlib import import_module

from django.conf import settings
from django.test import TestCase


class URLTestCase(TestCase):
    """
    This test case tests for a name string on all URLs.  Unnamed
    URLs will cause a TypeError in the metrics middleware.
    """
    pattern_attrs = ['urlpatterns', 'url_patterns']

    def test_url_names(self):
        urlconf = import_module(settings.ROOT_URLCONF)
        nameless = self.find_nameless_urls(urlconf)
        message = "URL regexes missing names: %s" % " ".join([n.regex.pattern for n in nameless])
        self.assertIs(len(nameless), 0, message)

    def find_nameless_urls(self, conf):
        nameless = []
        patterns = self.get_patterns(conf)
        for u in patterns:
            if self.has_patterns(u):
                nameless.extend(self.find_nameless_urls(u))
            else:
                if u.name is None:
                    nameless.append(u)
        return nameless

    def get_patterns(self, conf):
        for pa in self.pattern_attrs:
            if hasattr(conf, pa):
                return getattr(conf, pa)
        return []

    def has_patterns(self, conf):
        for pa in self.pattern_attrs:
            if hasattr(conf, pa):
                return True
        return False
