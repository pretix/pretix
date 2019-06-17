import pytest
from django.test import RequestFactory
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import Event, Organizer
from pretix.multidomain.middlewares import SessionMiddleware
from pretix.presale import checkoutflow


@pytest.fixture
def event():
    o = Organizer.objects.create(name='MRMCD', slug='mrmcd')
    e = Event.objects.create(
        organizer=o, name='MRMCD2015', slug='2015',
        date_from=now(), live=True
    )
    with scope(organizer=o):
        yield e


@pytest.fixture
def req_with_session():
    factory = RequestFactory()
    r = factory.get('/')
    SessionMiddleware().process_request(r)
    r.session.save()
    return r


@pytest.mark.django_db
def test_flow_order(event):
    orig_flow = checkoutflow.DEFAULT_FLOW
    checkoutflow.DEFAULT_FLOW = (
        checkoutflow.ConfirmStep, checkoutflow.PaymentStep, checkoutflow.QuestionsStep
    )
    flow = checkoutflow.get_checkout_flow(event)
    assert all(flow[i].priority <= flow[i + 1].priority for i in range(len(flow) - 1))
    checkoutflow.DEFAULT_FLOW = orig_flow


@pytest.mark.django_db
def test_double_linked_list(event):
    flow = checkoutflow.get_checkout_flow(event)
    assert all(flow[i]._next is flow[i + 1] for i in range(len(flow) - 1))
    assert all(flow[i + 1]._previous is flow[i] for i in range(len(flow) - 1))


@pytest.mark.django_db
def test_plugins_called(event, mocker):
    from pretix.presale.signals import checkout_flow_steps
    mocker.patch('pretix.presale.signals.checkout_flow_steps.send')
    checkoutflow.get_checkout_flow(event)
    checkout_flow_steps.send.assert_called_once_with(event)


def with_mocked_step(mocker, step, event):
    from pretix.presale.signals import checkout_flow_steps
    mocker.patch('pretix.presale.signals.checkout_flow_steps.send')
    checkout_flow_steps.send.return_value = [(None, step)]
    return checkoutflow.get_checkout_flow(event)


@pytest.mark.django_db
def test_plugins_max_priority(event, mocker):
    class MockingStep(checkoutflow.BaseCheckoutFlowStep):
        identifier = 'mocking'
        priority = 1001

    with pytest.raises(ValueError):
        with_mocked_step(mocker, MockingStep, event)


@pytest.mark.django_db
def test_plugin_in_order(event, mocker):
    class MockingStep(checkoutflow.BaseCheckoutFlowStep):
        identifier = 'mocking'
        priority = 100

    flow = with_mocked_step(mocker, MockingStep, event)
    assert isinstance(flow[0], checkoutflow.AddOnsStep)
    assert isinstance(flow[1], checkoutflow.QuestionsStep)
    assert isinstance(flow[2], MockingStep)
    assert isinstance(flow[3], checkoutflow.PaymentStep)
    assert isinstance(flow[4], checkoutflow.ConfirmStep)


@pytest.mark.django_db
def test_step_ignored(event, mocker, req_with_session):
    class MockingStep(checkoutflow.BaseCheckoutFlowStep):
        identifier = 'mocking'
        priority = 100

        def is_applicable(self, request):
            return False

    flow = with_mocked_step(mocker, MockingStep, event)
    req_with_session.event = event
    assert flow[1].get_next_applicable(req_with_session) is flow[4]
    # flow[3] is also skipped because no payment is required if there is no cart
    assert flow[1] is flow[4].get_prev_applicable(req_with_session)


@pytest.mark.django_db
def test_step_first_last(event):
    flow = checkoutflow.get_checkout_flow(event)
    assert flow[0].get_prev_applicable(req_with_session) is None
    assert flow[-1].get_next_applicable(req_with_session) is None
