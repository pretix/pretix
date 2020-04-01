import pytest
from django.conf import settings
from django.test.utils import override_settings
from django.utils.timezone import now

from pretix.base.models import Event, Organizer
from pretix.multidomain.models import KnownDomain


@pytest.fixture
def env():
    o = Organizer.objects.create(name='MRMCD', slug='mrmcd')
    event = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now(), live=True
    )
    event.get_cache().clear()
    settings.SITE_URL = 'http://example.com'
    return o, event


@pytest.mark.django_db
def test_control_only_on_main_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    r = client.get('/control/login', HTTP_HOST='foobar')
    assert r.status_code == 302
    assert r['Location'] == 'http://example.com/control/login'

    KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    r = client.get('/control/login', HTTP_HOST='barfoo')
    assert r.status_code == 302
    assert r['Location'] == 'http://example.com/control/login'


@pytest.mark.django_db
def test_append_slash(env, client):
    r = client.get('/control')
    assert r.status_code == 301
    assert r['Location'] == '/control/'


@pytest.mark.django_db
def test_unknown_domain(env, client):
    r = client.get('/control/login', HTTP_HOST='foobar')
    assert r.status_code == 400


@pytest.mark.django_db
def test_event_on_org_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    r = client.get('/2015/', HTTP_HOST='foobar')
    assert r.status_code == 200
    assert b'<meta property="og:title" content="MRMCD2015" />' in r.content


@pytest.mark.django_db
def test_event_on_custom_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0], event=env[1])
    r = client.get('/', HTTP_HOST='foobar')
    assert r.status_code == 200
    assert b'<meta property="og:title" content="MRMCD2015" />' in r.content


@pytest.mark.django_db
def test_path_without_trailing_slash_on_org_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    r = client.get('/widget/product_list', HTTP_HOST='foobar')
    assert r.status_code == 200


@pytest.mark.django_db
def test_event_with_org_domain_on_main_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    r = client.get('/mrmcd/2015/', HTTP_HOST='example.com')
    assert r.status_code == 302
    assert r['Location'] == 'http://foobar/2015/'


@pytest.mark.django_db
def test_event_with_custom_domain_on_main_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0], event=env[1])
    r = client.get('/mrmcd/2015/', HTTP_HOST='example.com')
    assert r.status_code == 302
    assert r['Location'] == 'http://foobar'


@pytest.mark.django_db
def test_event_with_custom_domain_on_org_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    r = client.get('/2015/', HTTP_HOST='foobar')
    assert r.status_code == 302
    assert r['Location'] == 'http://barfoo'


@pytest.mark.django_db
def test_organizer_with_org_domain_on_main_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    r = client.get('/mrmcd/', HTTP_HOST='example.com')
    assert r.status_code == 302
    assert r['Location'] == 'http://foobar'


@pytest.mark.django_db
def test_event_on_org_domain_only_with_wrong_organizer(env, client):
    organizer2 = Organizer.objects.create(name='Dummy', slug='dummy')
    Event.objects.create(
        organizer=organizer2, name='D1234', slug='1234',
        date_from=now(), live=True
    )
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    r = client.get('/dummy/1234/', HTTP_HOST='foobar')
    assert r.status_code == 404


@pytest.mark.django_db
def test_unknown_event_on_org_domain(env, client):
    organizer2 = Organizer.objects.create(name='Dummy', slug='dummy')
    Event.objects.create(
        organizer=organizer2, name='D1234', slug='1234',
        date_from=now(), live=True
    )
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    r = client.get('/1234/', HTTP_HOST='foobar')
    assert r.status_code == 404


@pytest.mark.django_db
def test_cookie_domain_on_org_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    client.post('/2015/cart/add', HTTP_HOST='foobar')
    r = client.get('/2015/', HTTP_HOST='foobar')
    assert r.client.cookies['pretix_csrftoken']['domain'] == ''
    assert r.client.cookies['pretix_session']['domain'] == ''


@pytest.mark.django_db
def test_cookie_domain_on_event_domain(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    KnownDomain.objects.create(domainname='barfoo', organizer=env[0], event=env[1])
    client.post('/cart/add', HTTP_HOST='barfoo')
    r = client.get('/', HTTP_HOST='barfoo')
    assert r.client.cookies['pretix_csrftoken']['domain'] == ''
    assert r.client.cookies['pretix_session']['domain'] == ''


@pytest.mark.django_db
def test_cookie_domain_on_main_domain(env, client):
    with override_settings(SESSION_COOKIE_DOMAIN='example.com'):
        client.post('/mrmcd/2015/cart/add', HTTP_HOST='example.com')
        r = client.get('/mrmcd/2015/', HTTP_HOST='example.com')
        assert r.client.cookies['pretix_csrftoken']['domain'] == 'example.com'
        assert r.client.cookies['pretix_session']['domain'] == 'example.com'


@pytest.mark.django_db
@override_settings(USE_X_FORWARDED_HOST=True)
def test_with_forwarded_host(env, client):
    KnownDomain.objects.create(domainname='foobar', organizer=env[0])
    r = client.get('/2015/', HTTP_X_FORWARDED_HOST='foobar')
    assert r.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("agent", [
    'Mozilla/5.0 (Linux; Android 4.4; Nexus 5 Build/_BuildID_) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 '
    'Chrome/79.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) '
    'CriOS/56.0.2924.75 Mobile/14E5239e Safari/602.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 13_0 like Mac OS X) AppleWebKit/603.1.23 (KHTML, like Gecko) Version/10.0 '
    'Mobile/14E5239e Safari/602.1',
    'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:47.0) Gecko/20100101 Firefox/47.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) AppleWebKit/534.59.10 (KHTML, like Gecko) Version/5.1.9 '
    'Safari/534.59.10',
    'Mozilla 5.0 (Windows NT 10.0; Win64; x64) AppleWebKit 537.36 (KHTML, like Gecko) Chrome 78.0.3904.97 Safari 537.36 OPR 65.0.3467.48',
    'Mozilla/5.0 (X11; Linux x86_64; rv:10.0) Gecko/20150101 Firefox/47.0 (Chrome)',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.0.0',
])
def test_cookie_samesite_none(env, client, agent):
    client.post('/mrmcd/2015/cart/add', HTTP_HOST='example.com', HTTP_USER_AGENT=agent,
                secure=True)
    r = client.get('/mrmcd/2015/', HTTP_HOST='example.com', HTTP_USER_AGENT=agent, secure=True)
    assert r.client.cookies['pretix_csrftoken']['samesite'] == 'None'
    assert r.client.cookies['pretix_session']['samesite'] == 'None'


@pytest.mark.django_db
@pytest.mark.parametrize("agent", [
    'Mozilla/5.0 (Linux; Android 4.4; Nexus 5 Build/_BuildID_) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 '
    'Chrome/52.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 12_3 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) '
    'CriOS/56.0.2924.75 Mobile/14E5239e Safari/602.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 12_0 like Mac OS X) AppleWebKit/603.1.23 (KHTML, like Gecko) Version/10.0 '
    'Mobile/14E5239e Safari/602.1',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_8) AppleWebKit/534.59.10 (KHTML, like Gecko) Version/5.1.9 '
    'Safari/534.59.10',
    'Mozilla/5.0 (Linux; Android 4.4.2; YOGA Tablet 2-1050L Build/KOT49H) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Version/4.0 Chrome/30.0.0.0 Safari/537.36 UCBrowser/3.1.0.403',
])
def test_cookie_samesite_none_only_on_compatible_browsers(env, client, agent):
    client.post('/mrmcd/2015/cart/add', HTTP_HOST='example.com', HTTP_USER_AGENT=agent, secure=True)
    r = client.get('/mrmcd/2015/', HTTP_HOST='example.com', HTTP_USER_AGENT=agent, secure=True)
    assert not r.client.cookies['pretix_csrftoken'].get('samesite')
