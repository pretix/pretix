#
# This file is part of pretix (Community Edition).
#
# Copyright (C) 2014-2020 Raphael Michel and contributors
# Copyright (C) 2020-2021 rami.io GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.
#
from datetime import date, datetime, timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.db.models import Max
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from lxml import etree

from pretix.base.models import ExchangeRate
from pretix.base.signals import periodic_task
from pretix.celery_app import app

SOURCE_NAMES = {
    None: _('European Central Bank'),  # backwards-compatibility
    'eu:ecb:eurofxref-daily': _('European Central Bank'),
    'cz:cnb:rate-fixing-daily': _('Czech National Bank'),
}


@receiver(signal=periodic_task)
def fetch_rates(sender, **kwargs):
    if not settings.FETCH_ECB_RATES:
        return

    source_tasks = {
        'eu:ecb:eurofxref-daily': fetch_ecb_rates,
        'cz:cnb:rate-fixing-daily': fetch_cnb_cz_rates,
    }

    for source_name, task in source_tasks.items():
        last_source_date = ExchangeRate.objects.filter(source=source_name).aggregate(m=Max('source_date'))['m']
        if last_source_date and last_source_date >= date.today():
            # We assume that the rates we fetch are only updated daily
            continue

        last_fetch_date = ExchangeRate.objects.filter(source=source_name).aggregate(m=Max('updated'))['m']
        if last_fetch_date and last_fetch_date >= now() - timedelta(hours=1):
            # Only try to fetch once per hour
            continue

        # Today's rate not yet published, let's try to fetch it
        task.apply_async()


@app.task()
def fetch_ecb_rates():
    """
    Fetches currency rates from the European Central Bank.
    """
    d = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
    r = requests.get(d)
    r.raise_for_status()

    # File looks like this:
    # <?xml version="1.0" encoding="UTF-8"?>
    # <gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
    #                  xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
    #   <gesmes:subject>Reference rates</gesmes:subject>
    #   <gesmes:Sender>
    #       <gesmes:name>European Central Bank</gesmes:name>
    #   </gesmes:Sender>
    #   <Cube>
    #       <Cube time="2023-02-14">
    #           <Cube currency="USD" rate="1.0759"/>
    #           ...
    #       </Cube>
    #   </Cube>
    # </gesmes:Envelope>

    root = etree.fromstring(r.content)
    namespaces = {
        'gesmes': 'http://www.gesmes.org/xml/2002-08-01',
        'eurofxref': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'
    }
    outercube = root.xpath('./eurofxref:Cube/eurofxref:Cube[@time]', namespaces=namespaces)[0]
    source_date = date.fromisoformat(outercube.get("time"))

    for cube in outercube.xpath('./eurofxref:Cube[@currency][@rate]', namespaces=namespaces):
        currency = cube.get('currency')
        rate = Decimal(cube.get('rate'))
        ExchangeRate.objects.update_or_create(
            source='eu:ecb:eurofxref-daily',
            source_currency='EUR',
            other_currency=currency,
            defaults=dict(
                source_date=source_date,
                rate=rate,
            )
        )


@app.task()
def fetch_cnb_cz_rates():
    """
    Fetches currency rates from the Czech National Bank.
    """
    d = f'https://www.cnb.cz/en/financial-markets/foreign-exchange-market/central-bank-exchange-rate-fixing/' \
        f'central-bank-exchange-rate-fixing/daily.txt?date={date.today().strftime("%d.%m.%Y")}'
    r = requests.get(d)
    r.raise_for_status()

    lines = r.text.splitlines()

    # File looks like this:
    # 14 Feb 2023 #32
    # Country|Currency|Amount|Code|Rate
    # Australia|dollar|1|AUD|15.412

    source_date = datetime.strptime(lines[0].split("#")[0].strip(), "%d %b %Y").date()

    for line in lines[2:]:
        country, currency, amount, code, rate = line.split("|")
        rate = Decimal(rate).quantize(Decimal('0.000001')) / int(amount)
        ExchangeRate.objects.update_or_create(
            source='cz:cnb:rate-fixing-daily',
            source_currency=code,
            other_currency='CZK',
            defaults=dict(
                source_date=source_date,
                rate=rate,
            )
        )
