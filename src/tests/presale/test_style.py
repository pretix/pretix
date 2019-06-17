import datetime
import os.path

from django.conf import settings
from django.test import TestCase, override_settings
from django_scopes import scopes_disabled

from pretix.base.models import Event, Organizer
from pretix.multidomain.models import KnownDomain
from pretix.presale.style import regenerate_css, regenerate_organizer_css


class StyleTest(TestCase):
    @scopes_disabled()
    def setUp(self):
        super().setUp()
        self.orga = Organizer.objects.create(name='CCC', slug='ccc')
        self.event = Event.objects.create(
            organizer=self.orga, name='30C3', slug='30c3',
            date_from=datetime.datetime(2013, 12, 26, tzinfo=datetime.timezone.utc),
            live=True
        )

    def test_organizer_generate_css_for_inherited_events(self):
        self.orga.settings.primary_color = "#33c33c"
        regenerate_organizer_css.apply(args=(self.orga.pk,))
        self.orga.settings.flush()
        assert self.orga.settings.presale_css_file
        with open(os.path.join(settings.MEDIA_ROOT, self.orga.settings.presale_css_file), 'r') as c:
            assert '#33c33c' in c.read()

        self.event.settings.flush()
        assert self.event.settings.presale_css_file
        with open(os.path.join(settings.MEDIA_ROOT, self.event.settings.presale_css_file), 'r') as c:
            assert '#33c33c' in c.read()

    def test_organizer_generate_css_only_for_inherited_events(self):
        self.orga.settings.primary_color = "#33c33c"
        self.event.settings.primary_color = "#34c34c"
        regenerate_organizer_css.apply(args=(self.orga.pk,))
        self.orga.settings.flush()
        assert self.orga.settings.presale_css_file
        with open(os.path.join(settings.MEDIA_ROOT, self.orga.settings.presale_css_file), 'r') as c:
            assert '#33c33c' in c.read()

        self.event.settings.flush()
        assert self.event.settings.presale_css_file
        with open(os.path.join(settings.MEDIA_ROOT, self.event.settings.presale_css_file), 'r') as c:
            assert '#34c34c' not in c.read()
            assert '#33c33c' not in c.read()

    def test_event_generate_css_individually(self):
        self.orga.settings.primary_color = "#33c33c"
        self.event.settings.primary_color = "#34c34c"
        regenerate_css.apply(args=(self.event.pk,))

        self.event.settings.flush()
        assert self.event.settings.presale_css_file
        with open(os.path.join(settings.MEDIA_ROOT, self.event.settings.presale_css_file), 'r') as c:
            assert '#34c34c' in c.read()
            assert '#33c33c' not in c.read()

        regenerate_organizer_css.apply(args=(self.orga.pk,))

        self.event.settings.flush()
        assert self.event.settings.presale_css_file
        with open(os.path.join(settings.MEDIA_ROOT, self.event.settings.presale_css_file), 'r') as c:
            assert '#34c34c' in c.read()
            assert '#33c33c' not in c.read()

    def test_event_generate_css_new_file(self):
        self.event.settings.primary_color = "#34c34c"
        regenerate_css.apply(args=(self.event.pk,))

        self.event.settings.flush()
        fname = self.event.settings.presale_css_file

        self.event.settings.primary_color = "#ff00ff"
        regenerate_css.apply(args=(self.event.pk,))
        self.event.settings.flush()
        assert self.event.settings.presale_css_file != fname

    def test_event_generate_css_cache_file(self):
        self.event.settings.primary_color = "#34c34c"
        regenerate_css.apply(args=(self.event.pk,))

        self.event.settings.flush()
        fname = self.event.settings.presale_css_file

        self.event.settings.primary_color = "#34c34c"
        regenerate_css.apply(args=(self.event.pk,))
        self.event.settings.flush()
        assert self.event.settings.presale_css_file == fname

    @override_settings(
        MEDIA_URL="https://usercontent.pretix.space/media/",
        SITE_URL="https://pretix.eu"
    )
    def test_seperate_media_domain(self):
        self.event.settings.primary_color = "#34c34c"
        regenerate_css.apply(args=(self.event.pk,))
        self.event.settings.flush()
        with open(os.path.join(settings.MEDIA_ROOT, self.event.settings.presale_css_file), 'r') as c:
            assert 'https://pretix.eu/static/' in c.read()

    @override_settings(
        MEDIA_URL="https://usercontent.pretix.space/media/",
        SITE_URL="https://pretix.eu"
    )
    def test_seperate_media_domain_and_organizer_domain(self):
        KnownDomain.objects.create(domainname="test.pretix.eu", organizer=self.orga)

        self.event.settings.primary_color = "#34c34c"
        regenerate_css.apply(args=(self.event.pk,))
        self.event.settings.flush()
        with open(os.path.join(settings.MEDIA_ROOT, self.event.settings.presale_css_file), 'r') as c:
            assert 'https://test.pretix.eu/static/' in c.read()

    @override_settings(
        STATIC_URL="https://static.pretix.files/static/",
        MEDIA_URL="https://usercontent.pretix.space/media/",
        SITE_URL="https://pretix.eu"
    )
    def test_seperate_media_domain_and_static_domain(self):
        KnownDomain.objects.create(domainname="test.pretix.eu", organizer=self.orga)

        self.event.settings.primary_color = "#34c34c"
        regenerate_css.apply(args=(self.event.pk,))
        self.event.settings.flush()
        with open(os.path.join(settings.MEDIA_ROOT, self.event.settings.presale_css_file), 'r') as c:
            assert 'https://static.pretix.files/static/' in c.read()
            assert 'https://test.pretix.eu/static/' not in c.read()
