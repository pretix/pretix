import copy
import datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.utils.timezone import now
from pytz import UTC

from pretix.base.models import Question
from pretix.base.models.orders import CartPosition


@pytest.fixture
def item(event):
    return event.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def item2(event2):
    return event2.items.create(name="Budget Ticket", default_price=23)


@pytest.fixture
def taxrule(event):
    return event.tax_rules.create(rate=Decimal('19.00'))


@pytest.fixture
def question(event, item):
    q = event.questions.create(question="T-Shirt size", type="S", identifier="ABC")
    q.items.add(item)
    q.options.create(answer="XL", identifier="LVETRWVU")
    return q


@pytest.fixture
def question2(event2, item2):
    q = event2.questions.create(question="T-Shirt size", type="S", identifier="ABC")
    q.items.add(item2)
    return q


@pytest.fixture
def quota(event, item):
    q = event.quotas.create(name="Budget Quota", size=200)
    q.items.add(item)
    return q


TEST_CARTPOSITION_RES = {
    'id': 1,
    'cart_id': 'aaa@api',
    'item': 1,
    'variation': None,
    'price': '23.00',
    'attendee_name_parts': {'full_name': 'Peter'},
    'attendee_name': 'Peter',
    'attendee_email': None,
    'voucher': None,
    'addon_to': None,
    'subevent': None,
    'datetime': '2018-06-11T10:00:00Z',
    'expires': '2018-06-11T10:00:00Z',
    'includes_tax': True,
    'answers': []
}


@pytest.mark.django_db
def test_cp_list(token_client, organizer, event, item, taxrule, question):
    testtime = datetime.datetime(2018, 6, 11, 10, 0, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        cr = CartPosition.objects.create(
            event=event, cart_id="aaa", item=item,
            price=23, attendee_name_parts={'full_name': 'Peter'},
            datetime=datetime.datetime(2018, 6, 11, 10, 0, 0, 0),
            expires=datetime.datetime(2018, 6, 11, 10, 0, 0, 0)
        )
    res = dict(TEST_CARTPOSITION_RES)
    res["id"] = cr.pk
    res["item"] = item.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/cartpositions/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [] == resp.data['results']


@pytest.mark.django_db
def test_cp_list_api(token_client, organizer, event, item, taxrule, question):
    testtime = datetime.datetime(2018, 6, 11, 10, 0, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        cr = CartPosition.objects.create(
            event=event, cart_id="aaa@api", item=item,
            price=23, attendee_name_parts={'full_name': 'Peter'},
            datetime=datetime.datetime(2018, 6, 11, 10, 0, 0, 0),
            expires=datetime.datetime(2018, 6, 11, 10, 0, 0, 0)
        )
    res = dict(TEST_CARTPOSITION_RES)
    res["id"] = cr.pk
    res["item"] = item.pk

    resp = token_client.get('/api/v1/organizers/{}/events/{}/cartpositions/'.format(organizer.slug, event.slug))
    assert resp.status_code == 200
    assert [res] == resp.data['results']


@pytest.mark.django_db
def test_cp_detail(token_client, organizer, event, item, taxrule, question):
    testtime = datetime.datetime(2018, 6, 11, 10, 0, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        cr = CartPosition.objects.create(
            event=event, cart_id="aaa@api", item=item,
            price=23, attendee_name_parts={'full_name': 'Peter'},
            datetime=datetime.datetime(2018, 6, 11, 10, 0, 0, 0),
            expires=datetime.datetime(2018, 6, 11, 10, 0, 0, 0)
        )
    res = dict(TEST_CARTPOSITION_RES)
    res["id"] = cr.pk
    res["item"] = item.pk
    resp = token_client.get('/api/v1/organizers/{}/events/{}/cartpositions/{}/'.format(organizer.slug, event.slug,
                                                                                       cr.pk))
    assert resp.status_code == 200
    assert res == resp.data


@pytest.mark.django_db
def test_cp_delete(token_client, organizer, event, item, taxrule, question):
    testtime = datetime.datetime(2018, 6, 11, 10, 0, 0, 0, tzinfo=UTC)

    with mock.patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = testtime
        cr = CartPosition.objects.create(
            event=event, cart_id="aaa@api", item=item,
            price=23, attendee_name_parts={'full_name': 'Peter'},
            datetime=datetime.datetime(2018, 6, 11, 10, 0, 0, 0),
            expires=datetime.datetime(2018, 6, 11, 10, 0, 0, 0)
        )
    res = dict(TEST_CARTPOSITION_RES)
    res["id"] = cr.pk
    res["item"] = item.pk
    resp = token_client.delete('/api/v1/organizers/{}/events/{}/cartpositions/{}/'.format(organizer.slug, event.slug,
                                                                                          cr.pk))
    assert resp.status_code == 204


CARTPOS_CREATE_PAYLOAD = {
    'cart_id': 'aaa@api',
    'item': 1,
    'variation': None,
    'price': '23.00',
    'attendee_name_parts': {'full_name': 'Peter'},
    'attendee_email': None,
    'addon_to': None,
    'subevent': None,
    'expires': '2018-06-11T10:00:00Z',
    'includes_tax': True,
    'answers': []
}


@pytest.mark.django_db
def test_cartpos_create(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    cp = CartPosition.objects.get(pk=resp.data['id'])
    assert cp.price == Decimal('23.00')
    assert cp.item == item
    assert cp.attendee_name_parts == {'full_name': 'Peter'}


@pytest.mark.django_db
def test_cartpos_create_name_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    res['attendee_name'] = None
    del res['attendee_name_parts']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    cp = CartPosition.objects.get(pk=resp.data['id'])
    assert cp.price == Decimal('23.00')
    assert cp.item == item
    assert cp.attendee_name_parts == {}


@pytest.mark.django_db
def test_cartpos_create_legacy_name(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    res['attendee_name'] = 'Peter'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    del res['attendee_name_parts']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    cp = CartPosition.objects.get(pk=resp.data['id'])
    assert cp.price == Decimal('23.00')
    assert cp.item == item
    assert cp.attendee_name_parts == {'_legacy': 'Peter'}


@pytest.mark.django_db
def test_cartpos_cart_id_noapi(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    res['cart_id'] = 'aaa'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_cartpos_cart_id_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    del res['cart_id']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    cp = CartPosition.objects.get(pk=resp.data['id'])
    assert cp.price == Decimal('23.00')
    assert cp.item == item
    assert len(cp.cart_id) > 48


@pytest.mark.django_db
def test_cartpos_create_subevent_validation(token_client, organizer, event, item, subevent, subevent2, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'subevent': ['You need to set a subevent.']}

    res['subevent'] = subevent2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'subevent': ['The specified subevent does not belong to this event.']}


@pytest.mark.django_db
def test_cartpos_create_item_validation(token_client, organizer, event, item, item2, quota, question):
    item.active = False
    item.save()
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'item': ['The specified item is not active.']}
    item.active = True
    item.save()

    res['item'] = item2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'item': ['The specified item does not belong to this event.']}

    var2 = item2.variations.create(value="A")

    res['item'] = item.pk
    res['variation'] = var2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'non_field_errors': ['You cannot specify a variation for this item.']}

    var1 = item.variations.create(value="A")
    res['item'] = item.pk
    res['variation'] = var1.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == ['The product "Budget Ticket" is not assigned to a quota.']

    quota.variations.add(var1)
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201

    res['variation'] = var2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'non_field_errors': ['The specified variation does not belong to the specified item.']}

    res['variation'] = None
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'non_field_errors': ['You should specify a variation for this item.']}


@pytest.mark.django_db
def test_cartpos_expires_optional(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk
    del res['expires']
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    cp = CartPosition.objects.get(pk=resp.data['id'])
    assert cp.price == Decimal('23.00')
    assert cp.item == item
    assert cp.expires - now() > datetime.timedelta(minutes=25)
    assert cp.expires - now() < datetime.timedelta(minutes=35)


@pytest.mark.django_db
def test_cartpos_create_answer_validation(token_client, organizer, event, item, quota, question, question2):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['answers'] = [{
        "question": 1,
        "answer": "S",
        "options": []
    }]

    res['item'] = item.pk
    res['answers'][0]['question'] = question2.pk
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'answers': [{'question': ['The specified question does not belong to this event.']}]}

    res['answers'][0]['question'] = question.pk
    res['answers'][0]['options'] = [question.options.first().pk]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'answers': [{'non_field_errors': ['You should not specify options if the question is not of a choice type.']}]}

    question.type = Question.TYPE_CHOICE
    question.save()
    res['answers'][0]['options'] = []
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'answers': [{'non_field_errors': ['You need to specify options if the question is of a choice type.']}]}

    question.options.create(answer="L")
    res['answers'][0]['options'] = [
        question.options.first().pk,
        question.options.last().pk,
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'answers': [{'non_field_errors': ['You can specify at most one option for this question.']}]}

    question.type = Question.TYPE_FILE
    question.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'answers': [{'non_field_errors': ['File uploads are currently not supported via the API.']}]}

    question.type = Question.TYPE_CHOICE_MULTIPLE
    question.save()
    res['answers'][0]['options'] = [
        question.options.first().pk,
        question.options.last().pk,
    ]
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    pos = CartPosition.objects.get(pk=resp.data['id'])
    answ = pos.answers.first()
    assert answ.question == question
    assert answ.answer == "XL, L"

    question.type = Question.TYPE_NUMBER
    question.save()
    res['answers'][0]['options'] = []
    res['answers'][0]['answer'] = '3.45'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    pos = CartPosition.objects.get(pk=resp.data['id'])
    answ = pos.answers.first()
    assert answ.answer == "3.45"

    question.type = Question.TYPE_NUMBER
    question.save()
    res['answers'][0]['options'] = []
    res['answers'][0]['answer'] = 'foo'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'answers': [{'non_field_errors': ['A valid number is required.']}]}

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['answers'][0]['options'] = []
    res['answers'][0]['answer'] = 'True'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    pos = CartPosition.objects.get(pk=resp.data['id'])
    answ = pos.answers.first()
    assert answ.answer == "True"

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['answers'][0]['answer'] = '0'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    pos = CartPosition.objects.get(pk=resp.data['id'])
    answ = pos.answers.first()
    assert answ.answer == "False"

    question.type = Question.TYPE_BOOLEAN
    question.save()
    res['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'answers': [{'non_field_errors': ['Please specify "true" or "false" for boolean questions.']}]}

    question.type = Question.TYPE_DATE
    question.save()
    res['answers'][0]['answer'] = '2018-05-14'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    pos = CartPosition.objects.get(pk=resp.data['id'])
    answ = pos.answers.first()
    assert answ.answer == "2018-05-14"

    question.type = Question.TYPE_DATE
    question.save()
    res['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {
        'answers': [{'non_field_errors': ['Date has wrong format. Use one of these formats instead: YYYY-MM-DD.']}]}

    question.type = Question.TYPE_DATETIME
    question.save()
    res['answers'][0]['answer'] = '2018-05-14T13:00:00Z'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    pos = CartPosition.objects.get(pk=resp.data['id'])
    answ = pos.answers.first()
    assert answ.answer == "2018-05-14 13:00:00+00:00"

    question.type = Question.TYPE_DATETIME
    question.save()
    res['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'answers': [{'non_field_errors': [
        'Datetime has wrong format. Use one of these formats instead: '
        'YYYY-MM-DDThh:mm[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z].']}]}

    question.type = Question.TYPE_TIME
    question.save()
    res['answers'][0]['answer'] = '13:00:00'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 201
    pos = CartPosition.objects.get(pk=resp.data['id'])
    answ = pos.answers.first()
    assert answ.answer == "13:00:00"

    question.type = Question.TYPE_TIME
    question.save()
    res['answers'][0]['answer'] = 'bla'
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == {'answers': [
        {'non_field_errors': ['Time has wrong format. Use one of these formats instead: hh:mm[:ss[.uuuuuu]].']}]}


@pytest.mark.django_db
def test_cartpos_create_quota_validation(token_client, organizer, event, item, quota, question):
    res = copy.deepcopy(CARTPOS_CREATE_PAYLOAD)
    res['item'] = item.pk

    quota.size = 0
    quota.save()
    resp = token_client.post(
        '/api/v1/organizers/{}/events/{}/cartpositions/'.format(
            organizer.slug, event.slug
        ), format='json', data=res
    )
    assert resp.status_code == 400
    assert resp.data == ['There is not enough quota available on quota "Budget Quota" to perform the operation.']
