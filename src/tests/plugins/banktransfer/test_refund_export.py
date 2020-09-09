from datetime import timedelta
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from django.core import mail as djmail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretix.base.models import (
    Event, Item, Order, OrderFee, OrderPayment, OrderPosition, Organizer,
    Quota, Team, User,
)
from pretix.plugins.banktransfer.models import BankImportJob, BankTransaction
from pretix.plugins.banktransfer.tasks import process_banktransfers
from pretix.plugins.banktransfer.views import _unite_transaction_rows, _row_key_func


def test_unite_transaction_rows():
    rows = sorted([
        {
            'payer': "Abc Def",
            'iban': 'DE12345678901234567890',
            'bic': 'HARKE9000',
            'id': "ROLLA-R-1",
            'amount': Decimal("42.23"),
        },
        {
            'payer': "First Last",
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': "PARTY-R-1",
            'amount': Decimal("6.50"),
        }
    ], key=_row_key_func)

    assert _unite_transaction_rows(rows) == rows

    rows = sorted(rows + [
        {
            'payer': "Abc Def",
            'iban': 'DE12345678901234567890',
            'bic': 'HARKE9000',
            'id': "ROLLA-R-1",
            'amount': Decimal("7.77"),
        },
        {
            'payer': "Another Last",
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': "PARTY-R-2",
            'amount': Decimal("13.50"),
        }
    ], key=_row_key_func)

    assert _unite_transaction_rows(rows) == sorted([
        {
            'payer': "Abc Def",
            'iban': 'DE12345678901234567890',
            'bic': 'HARKE9000',
            'id': "ROLLA-R-1",
            'amount': Decimal("50.00"),
        },
        {
            'payer': 'Another Last, First Last',
            'iban': 'DE111111111111111111111',
            'bic': 'ikswez2020',
            'id': 'PARTY-R-2, PARTY-R-1',
            'amount': Decimal('20.00'),
        }], key=_row_key_func)
