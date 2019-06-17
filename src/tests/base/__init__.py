from bs4 import BeautifulSoup
from django.test import TestCase


class SoupTest(TestCase):

    def get_doc(self, *args, **kwargs):
        response = self.client.get(*args, **kwargs)
        return BeautifulSoup(response.render().content, "lxml")

    def post_doc(self, *args, **kwargs):
        kwargs['follow'] = True
        response = self.client.post(*args, **kwargs)
        try:
            return BeautifulSoup(response.render().content, "lxml")
        except AttributeError:
            return BeautifulSoup(response.content, "lxml")


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
        elif field.has_attr('name'):
            # single element name/value fields
            data[field['name']] = field.get('value', '')
            continue

    # textareas
    for textarea in soup.findAll('textarea'):
        data[textarea['name']] = textarea.text or ''

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
