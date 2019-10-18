import pytest

from pretix.base.models import Organizer, Team, User


@pytest.fixture
def organizer():
    return Organizer.objects.create(name='Dummy', slug='dummy')


@pytest.fixture
def organizer2():
    return Organizer.objects.create(name='Partner', slug='partner')


@pytest.fixture
def gift_card(organizer):
    gc = organizer.issued_gift_cards.create(currency="EUR")
    gc.transactions.create(value=42)
    return gc


@pytest.fixture
def admin_user(organizer):
    u = User.objects.create_user('dummy@dummy.dummy', 'dummy')
    admin_team = Team.objects.create(organizer=organizer, can_manage_gift_cards=True, name='Admin team')
    admin_team.members.add(u)
    return u


@pytest.fixture
def team2(admin_user, organizer2):
    admin_team = Team.objects.create(organizer=organizer2, can_manage_gift_cards=True, name='Admin team')
    admin_team.members.add(admin_user)


@pytest.mark.django_db
def test_list_of_cards(organizer, admin_user, client, gift_card):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/giftcards')
    assert gift_card.secret in resp.content.decode()
    resp = client.get('/control/organizer/dummy/giftcards?query=' + gift_card.secret[:3])
    assert gift_card.secret in resp.content.decode()
    resp = client.get('/control/organizer/dummy/giftcards?query=1234_FOO')
    assert gift_card.secret not in resp.content.decode()


@pytest.mark.django_db
def test_card_detail_view(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.get('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk))
    assert gift_card.secret in resp.content.decode()
    assert '42.00' in resp.content.decode()


@pytest.mark.django_db
def test_card_add(organizer, admin_user, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    resp = client.post('/control/organizer/dummy/giftcard/add', {
        'currency': 'EUR',
        'secret': 'FOOBAR',
        'value': '42.00',
        'testmode': 'on'
    }, follow=True)
    assert 'TEST MODE' in resp.content.decode()
    assert '42.00' in resp.content.decode()
    resp = client.post('/control/organizer/dummy/giftcard/add', {
        'currency': 'EUR',
        'secret': 'FOOBAR',
        'value': '42.00',
        'testmode': 'on'
    }, follow=True)
    assert 'has-error' in resp.content.decode()


@pytest.mark.django_db
def test_card_detail_view_transact(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk), {
        'value': '23.00'
    })
    assert gift_card.value == 23 + 42
    assert gift_card.all_logentries().count() == 1


@pytest.mark.django_db
def test_card_detail_view_transact_min_value(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk), {
        'value': '-50.00'
    })
    assert 'alert-danger' in r.rendered_content
    assert gift_card.value == 42


@pytest.mark.django_db
def test_card_detail_view_transact_invalid_value(organizer, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    r = client.post('/control/organizer/dummy/giftcard/{}/'.format(gift_card.pk), {
        'value': 'foo'
    })
    assert 'alert-danger' in r.rendered_content
    assert gift_card.value == 42


@pytest.mark.django_db
def test_manage_acceptance(organizer, organizer2, admin_user, gift_card, client, team2):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/giftcards'.format(gift_card.pk), {
        'add': organizer2.slug
    })
    assert organizer.gift_card_issuer_acceptance.filter(issuer=organizer2).exists()
    client.post('/control/organizer/dummy/giftcards'.format(gift_card.pk), {
        'del': organizer2.slug
    })
    assert not organizer.gift_card_issuer_acceptance.filter(issuer=organizer2).exists()


@pytest.mark.django_db
def test_manage_acceptance_permission_required(organizer, organizer2, admin_user, gift_card, client):
    client.login(email='dummy@dummy.dummy', password='dummy')
    client.post('/control/organizer/dummy/giftcards'.format(gift_card.pk), {
        'add': organizer2.slug
    })
    assert not organizer.gift_card_issuer_acceptance.filter(issuer=organizer2).exists()
