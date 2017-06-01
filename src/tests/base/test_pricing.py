from decimal import Decimal

import pytest
from django.utils.timezone import now

from pretix.base.models import Event, Organizer
from pretix.base.models.items import SubEventItem, SubEventItemVariation
from pretix.base.services.pricing import get_price


@pytest.fixture
def event():
    o = Organizer.objects.create(name='Dummy', slug='dummy')
    event = Event.objects.create(
        organizer=o, name='Dummy', slug='dummy',
        date_from=now()
    )
    return event


@pytest.fixture
def item(event):
    return event.items.create(name='Ticket', default_price=Decimal('23.00'))


@pytest.fixture
def variation(item):
    return item.variations.create(value='Premium', default_price=None)


@pytest.fixture
def voucher(event):
    return event.vouchers.create()


@pytest.fixture
def subevent(event):
    event.has_subevents = True
    event.save()
    return event.subevents.create(name='Foobar', date_from=now())


@pytest.mark.django_db
def test_base_item_default(item):
    assert get_price(item) == Decimal('23.00')


@pytest.mark.django_db
def test_base_item_subevent_no_entry(item, subevent):
    assert get_price(item, subevent=subevent) == Decimal('23.00')


@pytest.mark.django_db
def test_base_item_subevent_no_override(item, subevent):
    SubEventItem.objects.create(item=item, subevent=subevent, price=None)
    assert get_price(item, subevent=subevent) == Decimal('23.00')


@pytest.mark.django_db
def test_base_item_subevent_override(item, subevent):
    SubEventItem.objects.create(item=item, subevent=subevent, price=Decimal('24.00'))
    assert get_price(item, subevent=subevent) == Decimal('24.00')


@pytest.mark.django_db
def test_variation_with_default_item_price(item, variation):
    assert get_price(item, variation=variation) == Decimal('23.00')


@pytest.mark.django_db
def test_variation_with_specific_price(item, variation):
    variation.default_price = Decimal('24.00')
    assert get_price(item, variation=variation) == Decimal('24.00')


@pytest.mark.django_db
def test_variation_with_default_subevent_and_default_price(item, subevent, variation):
    SubEventItemVariation.objects.create(variation=variation, subevent=subevent, price=None)
    assert get_price(item, variation=variation, subevent=subevent) == Decimal('23.00')


@pytest.mark.django_db
def test_variation_with_subevent_and_default_price(item, subevent, variation):
    SubEventItemVariation.objects.create(variation=variation, subevent=subevent, price=Decimal('24.00'))
    assert get_price(item, variation=variation, subevent=subevent) == Decimal('24.00')


@pytest.mark.django_db
def test_variation_with_no_subevent_and_specific_price(item, subevent, variation):
    variation.default_price = Decimal('24.00')
    assert get_price(item, variation=variation, subevent=subevent) == Decimal('24.00')


@pytest.mark.django_db
def test_variation_with_default_subevent_and_specific_price(item, subevent, variation):
    variation.default_price = Decimal('24.00')
    SubEventItemVariation.objects.create(variation=variation, subevent=subevent, price=None)
    assert get_price(item, variation=variation, subevent=subevent) == Decimal('24.00')


@pytest.mark.django_db
def test_variation_with_subevent_and_specific_price(item, subevent, variation):
    variation.default_price = Decimal('24.00')
    SubEventItemVariation.objects.create(variation=variation, subevent=subevent, price=Decimal('26.00'))
    assert get_price(item, variation=variation, subevent=subevent) == Decimal('26.00')


@pytest.mark.django_db
def test_voucher_no_override(item, subevent, voucher):
    assert get_price(item, subevent=subevent, voucher=voucher) == Decimal('23.00')


@pytest.mark.django_db
def test_voucher_set_price(item, subevent, voucher):
    voucher.price_mode = 'set'
    voucher.value = Decimal('12.00')
    assert get_price(item, subevent=subevent, voucher=voucher) == Decimal('12.00')


@pytest.mark.django_db
def test_voucher_subtract(item, subevent, voucher):
    voucher.price_mode = 'subtract'
    voucher.value = Decimal('12.00')
    assert get_price(item, subevent=subevent, voucher=voucher) == Decimal('11.00')


@pytest.mark.django_db
def test_voucher_percent(item, subevent, voucher):
    voucher.price_mode = 'percent'
    voucher.value = Decimal('10.00')
    assert get_price(item, subevent=subevent, voucher=voucher) == Decimal('20.70')


@pytest.mark.django_db
def test_free_price_ignored_if_disabled(item):
    assert get_price(item, custom_price=Decimal('42.00')) == Decimal('23.00')


@pytest.mark.django_db
def test_free_price_ignored_if_lower(item):
    item.free_price = True
    assert get_price(item, custom_price=Decimal('12.00')) == Decimal('23.00')


@pytest.mark.django_db
def test_free_price_ignored_if_lower_than_voucher(item, voucher):
    voucher.price_mode = 'set'
    voucher.value = Decimal('50.00')
    assert get_price(item, voucher=voucher, custom_price=Decimal('40.00')) == Decimal('50.00')


@pytest.mark.django_db
def test_free_price_ignored_if_lower_than_subevent(item, subevent):
    item.free_price = True
    SubEventItem.objects.create(item=item, subevent=subevent, price=Decimal('50.00'))
    assert get_price(item, subevent=subevent, custom_price=Decimal('40.00')) == Decimal('50.00')


@pytest.mark.django_db
def test_free_price_ignored_if_lower_than_variation(item, variation):
    variation.default_price = Decimal('50.00')
    item.free_price = True
    assert get_price(item, variation=variation, custom_price=Decimal('40.00')) == Decimal('50.00')


@pytest.mark.django_db
def test_free_price_accepted(item):
    item.free_price = True
    assert get_price(item, custom_price=Decimal('42.00')) == Decimal('42.00')


@pytest.mark.django_db
def test_free_price_string(item):
    item.free_price = True
    assert get_price(item, custom_price='42,00') == Decimal('42.00')


@pytest.mark.django_db
def test_free_price_float(item):
    item.free_price = True
    assert get_price(item, custom_price=42.00) == Decimal('42.00')


@pytest.mark.django_db
def test_free_price_limit(item):
    item.free_price = True
    with pytest.raises(ValueError):
        get_price(item, custom_price=Decimal('200000000'))


@pytest.mark.django_db
def test_free_price_net(item):
    item.free_price = True
    item.tax_rate = 19
    assert get_price(item, custom_price=Decimal('100.00'), custom_price_is_net=True) == Decimal('119.00')
