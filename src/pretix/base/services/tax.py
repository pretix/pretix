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
from urllib.error import HTTPError

import vat_moss.errors
import vat_moss.id
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from zeep import Client, Transport
from zeep.cache import SqliteCache
from zeep.exceptions import Fault

from pretix.base.models.tax import cc_to_vat_prefix, is_eu_country

logger = logging.getLogger(__name__)


class VATIDError(Exception):
    def __init__(self, message):
        self.message = message


class VATIDFinalError(VATIDError):
    pass


class VATIDTemporaryError(VATIDError):
    pass


def _validate_vat_id_EU(vat_id, country_code):
    if vat_id[:2] != cc_to_vat_prefix(country_code):
        raise VATIDFinalError(_('Your VAT ID does not match the selected country.'))

    try:
        result = vat_moss.id.validate(vat_id)
        if result:
            country_code, normalized_id, company_name = result
            return normalized_id
    except (vat_moss.errors.InvalidError, ValueError):
        raise VATIDFinalError(_('This VAT ID is not valid. Please re-check your input.'))
    except vat_moss.errors.WebServiceUnavailableError:
        logger.exception('VAT ID checking failed for country {}'.format(country_code))
        raise VATIDTemporaryError(_(
            'Your VAT ID could not be checked, as the VAT checking service of '
            'your country is currently not available. We will therefore '
            'need to charge VAT on your invoice. You can get the tax amount '
            'back via the VAT reimbursement process.'
        ))
    except (vat_moss.errors.WebServiceError, HTTPError):
        logger.exception('VAT ID checking failed for country {}'.format(country_code))
        raise VATIDTemporaryError(_(
            'Your VAT ID could not be checked, as the VAT checking service of '
            'your country returned an incorrect result. We will therefore '
            'need to charge VAT on your invoice. Please contact support to '
            'resolve this manually.'
        ))


def _validate_vat_id_CH(vat_id, country_code):
    if vat_id[:3] != 'CHE':
        raise VATIDFinalError(_('Your VAT ID does not match the selected country.'))

    vat_id = re.sub('[^A-Z0-9]', '', vat_id.replace('HR', '').replace('MWST', ''))
    try:
        transport = Transport(cache=SqliteCache(os.path.join(settings.CACHE_DIR, "validate_vat_id_ch_zeep_cache.db")))
        client = Client(
            'https://www.uid-wse.admin.ch/V5.0/PublicServices.svc?wsdl',
            transport=transport
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
    country_code = str(country_code)
    if is_eu_country(country_code):
        return _validate_vat_id_EU(vat_id, country_code)
    elif country_code == 'CH':
        return _validate_vat_id_CH(vat_id, country_code)

    raise VATIDTemporaryError(f'VAT ID should not be entered for country {country_code}')
