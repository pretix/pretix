import os
import sys
import time

from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase
from selenium import webdriver

# could use Chrome, Firefox, etc... here
BROWSER = os.environ.get('TEST_BROWSER', 'PhantomJS')


class BrowserTest(StaticLiveServerTestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        settings.DEBUG = ('--debug' in sys.argv)

    def setUp(self):
        if hasattr(webdriver, BROWSER):
            self.driver = getattr(webdriver, BROWSER)()
        else:
            self.driver = webdriver.Remote(
                desired_capabilities=webdriver.DesiredCapabilities.CHROME,
                command_executor=BROWSER
            )
        self.driver.set_window_size(1920, 1080)
        self.driver.implicitly_wait(10)

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


class SoupTest(TestCase):

    def get_doc(self, *args, **kwargs):
        response = self.client.get(*args, **kwargs)
        return BeautifulSoup(response.rendered_content)

    def post_doc(self, *args, **kwargs):
        kwargs['follow'] = True
        response = self.client.post(*args, **kwargs)
        return BeautifulSoup(response.rendered_content)


def extract_form_fields(soup):
    """
    Turn a BeautifulSoup form in to a dict of fields and default values
    Inspiration: https://gist.github.com/simonw/104413
    """
    data = {}
    for field in soup.find_all('input'):
        # ignore submit/image with no name attribute
        if field['type'] in ('submit', 'image') and not field.has_attr('name'):
            continue

        if field['type'] in ('checkbox', 'radio'):
            if field.has_attr('checked'):
                data[field['name']] = field.get('value', 'on')

            continue
        else:
            # single element name/value fields
            data[field['name']] = field.get('value', '')
            continue

    # textareas
    for textarea in soup.findAll('textarea'):
        data[textarea['name']] = textarea.string or ''

    # select fields
    for select in soup.find_all('select'):
        value = ''
        options = select.find_all('option')
        is_multiple = select.has_attr('multiple')
        selected_options = [
            option for option in options
            if option.has_attr('selected')
        ]

        # If no select options, go with the first one
        if not selected_options and options:
            selected_options = [options[0]]

        if not is_multiple:
            assert (len(selected_options) < 2)
            if len(selected_options) == 1:
                value = selected_options[0]['value']
        else:
            value = [option['value'] for option in selected_options]

        data[select['name']] = value

    return data
