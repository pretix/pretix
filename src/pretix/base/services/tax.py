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
import logging
import os
import re
from collections import defaultdict
from decimal import Decimal
from xml.etree import ElementTree

import requests
import vat_moss.id
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from zeep import Client, Transport
from zeep.cache import SqliteCache
from zeep.exceptions import Fault

from pretix.base.decimal import round_decimal
from pretix.base.models import CartPosition, Event, OrderFee
from pretix.base.models.tax import TaxRule, cc_to_vat_prefix, is_eu_country

logger = logging.getLogger(__name__)
error_messages = {
    'unavailable': _(
        'Your VAT ID could not be checked, as the VAT checking service of '
        'your country is currently not available. We will therefore '
        'need to charge VAT on your invoice. You can get the tax amount '
        'back via the VAT reimbursement process.'
    ),
    'invalid': _('This VAT ID is not valid. Please re-check your input.'),
    'country_mismatch': _('Your VAT ID does not match the selected country.'),
}


class VATIDError(Exception):
    def __init__(self, message):
        self.message = message


class VATIDFinalError(VATIDError):
    pass


class VATIDTemporaryError(VATIDError):
    pass


def _validate_vat_id_NO(vat_id, country_code):
    # Inspired by vat_moss library
    if not vat_id.startswith("NO"):
        # prefix is not usually used in Norway, but expected by vat_moss library
        vat_id = "NO" + vat_id
    try:
        vat_id = vat_moss.id.normalize(vat_id)
    except ValueError:
        raise VATIDFinalError(error_messages['invalid'])

    if not vat_id or len(vat_id) < 3 or not re.match('^\\d{9}MVA$', vat_id[2:]):
        raise VATIDFinalError(error_messages['invalid'])

    organization_number = vat_id[2:].replace('MVA', '')
    validation_url = 'https://data.brreg.no/enhetsregisteret/api/enheter/%s' % organization_number

    try:
        response = requests.get(validation_url, timeout=10)
        if response.status_code in (404, 400):
            raise VATIDFinalError(error_messages['invalid'])

        response.raise_for_status()

        info = response.json()
        # This should never happen, but keeping it incase the API is changed
        if 'organisasjonsnummer' not in info or info['organisasjonsnummer'] != organization_number:
            logger.warning(
                'VAT ID checking failed for Norway due to missing or mismatching organisasjonsnummer in repsonse'
            )
            raise VATIDFinalError(error_messages['invalid'])
    except requests.RequestException:
        logger.exception('VAT ID checking failed for country {}'.format(country_code))
        raise VATIDTemporaryError(error_messages['unavailable'])
    else:
        return vat_id


def _validate_vat_id_EU(vat_id, country_code):
    # Inspired by vat_moss library
    try:
        vat_id = vat_moss.id.normalize(vat_id)
    except ValueError:
        raise VATIDFinalError(error_messages['invalid'])

    if not vat_id or len(vat_id) < 3:
        raise VATIDFinalError(error_messages['invalid'])

    number = vat_id[2:]

    if vat_id[:2] != cc_to_vat_prefix(country_code):
        raise VATIDFinalError(error_messages['country_mismatch'])

    if not re.match(vat_moss.id.ID_PATTERNS[cc_to_vat_prefix(country_code)]['regex'], number):
        raise VATIDFinalError(error_messages['invalid'])

    # We are relying on the country code of the normalized VAT-ID and not the user/InvoiceAddress-provided
    # VAT-ID, since Django and the EU have different ideas of which country is using which country code.
    # For example: For django and most people, Greece is GR. However, the VAT-service expects EL.
    payload = """
            <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
               <soapenv:Header/>
               <soapenv:Body>
                  <urn:checkVat>
                     <urn:countryCode>%s</urn:countryCode>
                     <urn:vatNumber>%s</urn:vatNumber>
                  </urn:checkVat>
               </soapenv:Body>
            </soapenv:Envelope>
    """.strip() % (vat_id[:2], number)

    try:
        response = requests.post(
            'https://ec.europa.eu/taxation_customs/vies/services/checkVatService',
            data=payload,
            timeout=10,
        )
        response.raise_for_status()

        return_xml = response.text

        try:
            envelope = ElementTree.fromstring(return_xml)
        except ElementTree.ParseError:
            logger.error(
                f'VAT ID checking failed for {country_code} due to XML parse error'
            )
            raise VATIDTemporaryError(error_messages['unavailable'])

        namespaces = {
            'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
            'vat': 'urn:ec.europa.eu:taxud:vies:services:checkVat:types'
        }
        valid_elements = envelope.findall('./soap:Body/vat:checkVatResponse/vat:valid', namespaces)
        if not valid_elements:
            logger.error(
                f'VAT ID checking failed for {country_code} due to missing <valid> tag, response was: {return_xml}'
            )
            raise VATIDTemporaryError(error_messages['unavailable'])

        if valid_elements[0].text.lower() != 'true':
            raise VATIDFinalError(error_messages['invalid'])

    except requests.RequestException:
        logger.exception('VAT ID checking failed for country {}'.format(country_code))
        raise VATIDTemporaryError(error_messages['unavailable'])
    else:
        return vat_id


def _validate_vat_id_CH(vat_id, country_code):
    if vat_id[:3] != 'CHE':
        raise VATIDFinalError(_('Your VAT ID does not match the selected country.'))

    vat_id = re.sub('[^A-Z0-9]', '', vat_id.replace('HR', '').replace('MWST', ''))
    try:
        transport = Transport(
            cache=SqliteCache(os.path.join(settings.CACHE_DIR, "validate_vat_id_ch_zeep_cache.db")),
            timeout=10
        )
        client = Client(
            'https://www.uid-wse.admin.ch/V5.0/PublicServices.svc?wsdl',
            transport=transport,
        )
        result = client.service.ValidateUID(uid=vat_id)
    except Fault as e:
        if e.message == 'Data_validation_failed':
            raise VATIDFinalError(_('This VAT ID is not valid. Please re-check your input.'))
        elif e.message == 'Request_limit_exceeded':
            logger.exception('VAT ID checking failed for country {} due to request limit'.format(country_code))
            raise VATIDTemporaryError(_(
                'Your VAT ID could not be checked, as the VAT checking service of '
                'your country returned an incorrect result. We will therefore '
                'need to charge VAT on your invoice. Please contact support to '
                'resolve this manually.'
            ))
        else:
            logger.exception('VAT ID checking failed for country {}'.format(country_code))
            raise VATIDTemporaryError(_(
                'Your VAT ID could not be checked, as the VAT checking service of '
                'your country returned an incorrect result. We will therefore '
                'need to charge VAT on your invoice. Please contact support to '
                'resolve this manually.'
            ))
    except:
        logger.exception('VAT ID checking failed for country {}'.format(country_code))
        raise VATIDTemporaryError(_(
            'Your VAT ID could not be checked, as the VAT checking service of '
            'your country is currently not available. We will therefore '
            'need to charge VAT on your invoice. You can get the tax amount '
            'back via the VAT reimbursement process.'
        ))
    else:
        if not result:
            raise VATIDFinalError(_('This VAT ID is not valid. Please re-check your input.'))
        return vat_id


def validate_vat_id(vat_id, country_code):
    if not vat_id:
        return vat_id
    country_code = str(country_code)
    if is_eu_country(country_code):
        return _validate_vat_id_EU(vat_id, country_code)
    elif country_code == 'CH':
        return _validate_vat_id_CH(vat_id, country_code)
    elif country_code == 'NO':
        return _validate_vat_id_NO(vat_id, country_code)

    raise VATIDTemporaryError(f'VAT ID should not be entered for country {country_code}')


def split_fee_for_taxes(positions: list, fee_value: Decimal, event: Event):
    """
    Given a list of either OrderPosition, OrderFee or CartPosition objects and the total value
    of a fee, this will return a list of [(tax_rule, fee_value)] tuples that distributes the
    taxes over the same tax rules as the positions with a value representative to the value
    the tax rule.

    Since the input fee_value is a gross value, we also split it by the gross percentages of
    positions. This will lead to the same result as if we split the net value by net percentages,
    but is easier to compute.
    """
    d = defaultdict(lambda: Decimal("0.00"))
    tax_rule_zero = TaxRule.zero()
    trs = {}
    for p in positions:
        if isinstance(p, CartPosition):
            tr = p.item.tax_rule
            v = p.price
        elif isinstance(p, OrderFee):
            tr = p.tax_rule
            v = p.value
        else:
            tr = p.tax_rule
            v = p.price
        if not tr:
            tr = tax_rule_zero
        # use tr.pk as key as tax_rule_zero is not hashable
        d[tr.pk] += v
        trs[tr.pk] = tr

    base_values = sorted([(trs[key], value) for key, value in d.items()], key=lambda t: t[0].rate)
    sum_base = sum(value for key, value in base_values)
    if sum_base:
        fee_values = [
            (key, round_decimal(fee_value * value / sum_base, event.currency))
            for key, value in base_values
        ]
        sum_fee = sum(value for key, value in fee_values)

        # If there are rounding differences, we fix them up, but always leaning to the benefit of the tax
        # authorities
        if sum_fee > fee_value:
            fee_values[0] = (
                fee_values[0][0],
                fee_values[0][1] + (fee_value - sum_fee),
            )
        elif sum_fee < fee_value:
            fee_values[-1] = (
                fee_values[-1][0],
                fee_values[-1][1] + (fee_value - sum_fee),
            )
    elif len(d) == 1:
        # Rare edge case: All positions are 0-valued, but have a common tax rate. Could happen e.g. with a discount
        # that reduces all positions to 0, but not the shipping fees. Let's use that tax rate!
        fee_values = [(list(trs.values())[0], fee_value)]
    else:
        # All positions are zero-valued, and we have no clear tax rate, so we use the default tax rate.
        fee_values = [(event.cached_default_tax_rule or tax_rule_zero, fee_value)]
    return fee_values
