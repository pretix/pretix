import os
import sys
import time
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from django.conf import settings
from selenium import webdriver


# could use Chrome, Firefox, etc... here
BROWSER = os.environ.get('TEST_BROWSER', 'PhantomJS')


class BrowserTest(StaticLiveServerTestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        settings.DEBUG = ('--debug' in sys.argv)

    def setUp(self):
        self.driver = getattr(webdriver, BROWSER)()
        self.driver.set_window_size(1920, 1080)
        self.driver.implicitly_wait(3)

    def tearDown(self):
        self.driver.quit()

    def scroll_into_view(self, element):
        """Scroll element into view"""
        y = element.location['y']
        self.driver.execute_script('window.scrollTo(0, {0})'.format(y))

    def scroll_and_click(self, element):
        self.scroll_into_view(element)
        time.sleep(0.5)
        element.click()
