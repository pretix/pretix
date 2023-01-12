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
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from localflavor.ar.forms import ARPostalCodeField
from localflavor.at.forms import ATZipCodeField
from localflavor.au.forms import AUPostCodeField
from localflavor.be.forms import BEPostalCodeField
from localflavor.br.forms import BRZipCodeField
from localflavor.ca.forms import CAPostalCodeField
from localflavor.ch.forms import CHZipCodeField
from localflavor.cn.forms import CNPostCodeField
from localflavor.cu.forms import CUPostalCodeField
from localflavor.cz.forms import CZPostalCodeField
from localflavor.de.forms import DEZipCodeField
from localflavor.dk.forms import DKPostalCodeField
from localflavor.ee.forms import EEZipCodeField
from localflavor.es.forms import ESPostalCodeField
from localflavor.fi.forms import FIZipCodeField
from localflavor.fr.forms import FRZipCodeField
from localflavor.gb.forms import GBPostcodeField
from localflavor.gr.forms import GRPostalCodeField
from localflavor.hr.forms import HRPostalCodeField
from localflavor.ie.forms import EircodeField
from localflavor.il.forms import ILPostalCodeField
from localflavor.in_.forms import INZipCodeField
from localflavor.ir.forms import IRPostalCodeField
from localflavor.is_.is_postalcodes import IS_POSTALCODES
from localflavor.it.forms import ITZipCodeField
from localflavor.jp.forms import JPPostalCodeField
from localflavor.lt.forms import LTPostalCodeField
from localflavor.lv.forms import LVPostalCodeField
from localflavor.ma.forms import MAPostalCodeField
from localflavor.mt.forms import MTPostalCodeField
from localflavor.mx.forms import MXZipCodeField
from localflavor.nl.forms import NLZipCodeField
from localflavor.no.forms import NOZipCodeField
from localflavor.nz.forms import NZPostCodeField
from localflavor.pk.forms import PKPostCodeField
from localflavor.pl.forms import PLPostalCodeField
from localflavor.pt.forms import PTZipCodeField
from localflavor.ro.forms import ROPostalCodeField
from localflavor.ru.forms import RUPostalCodeField
from localflavor.se.forms import SEPostalCodeField
from localflavor.sg.forms import SGPostCodeField
from localflavor.si.si_postalcodes import SI_POSTALCODES
from localflavor.sk.forms import SKPostalCodeField
from localflavor.tr.forms import TRPostalCodeField
from localflavor.ua.forms import UAPostalCodeField
from localflavor.us.forms import USZipCodeField
from localflavor.za.forms import ZAPostCodeField

from pretix.base.settings import COUNTRIES_WITH_STATE_IN_ADDRESS

_validator_classes = defaultdict(list)

COUNTRIES_WITH_STREET_ZIPCODE_AND_CITY_REQUIRED = {
    # We don't presume this for countries we don't have knowledge about, there are countries in the
    # world e.g. without zipcodes
    'AR', 'AT', 'AU', 'BE', 'BR', 'CA', 'CH', 'CN', 'CU', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR',
    'GB', 'GR', 'HR', 'IE', 'IL', 'IN', 'IR', 'IS', 'IT', 'JP', 'LT', 'LV', 'MA', 'MT', 'MX', 'NL',
    'NO', 'NZ', 'PK', 'PL', 'PT', 'RO', 'RU', 'SE', 'SG', 'SI', 'SK', 'TR', 'UA', 'US', 'ZA',
}


def validate_address(address: dict, all_optional=False):
    """
    :param address: A dictionary with at least the entries ``street``, ``zipcode``, ``city``, ``country``,
                    ``state``
    :return: The dictionary, possibly with changes
    """
    if not address.get('street') and not address.get('zipcode') and not address.get('city'):
        # Consider the actual address part to be empty, no further validation necessary, if the
        # address should be required, it's the callers job to validate that at least one of these
        # fields is filled
        return address

    if not address.get('country'):
        raise ValidationError({'country': [_('This field is required.')]})

    if str(address['country']) in COUNTRIES_WITH_STATE_IN_ADDRESS and not address.get('state') and not all_optional:
        raise ValidationError({'state': [_('This field is required.')]})

    if str(address['country']) in COUNTRIES_WITH_STREET_ZIPCODE_AND_CITY_REQUIRED and not all_optional:
        for f in ('street', 'zipcode', 'city'):
            if not address.get(f):
                raise ValidationError({f: [_('This field is required.')]})

    for klass in _validator_classes[str(address['country'])]:
        validator = klass()
        try:
            if address.get('zipcode'):
                address['zipcode'] = validator.validate_zipcode(address['zipcode'])
        except ValidationError as e:
            raise ValidationError({'zipcode': list(e)})

    return address


def register_validator_for(country):
    def inner(klass):
        _validator_classes[country].append(klass)
        return klass

    return inner


class BaseValidator:
    required_fields = []

    def validate_zipcode(self, value):
        return value


"""
Currently, mostly have validators that are auto-generated from django-localflavor
but custom ones can be added like this:

@register_validator_for('DE')
class DEValidator(BaseValidator):
    def validate_zipcode(value):
        return value

In the future, we can also add additional methods to validate that e.g. a city
is plausible for a given zip code.
"""

_zip_code_fields = {
    'AR': ARPostalCodeField,
    'AT': ATZipCodeField,
    'AU': AUPostCodeField,
    'BE': BEPostalCodeField,
    'BR': BRZipCodeField,
    'CA': CAPostalCodeField,
    'CH': CHZipCodeField,
    'CN': CNPostCodeField,
    'CU': CUPostalCodeField,
    'CZ': CZPostalCodeField,
    'DE': DEZipCodeField,
    'DK': DKPostalCodeField,
    'EE': EEZipCodeField,
    'ES': ESPostalCodeField,
    'FI': FIZipCodeField,
    'FR': FRZipCodeField,
    'GB': GBPostcodeField,
    'GR': GRPostalCodeField,
    'HR': HRPostalCodeField,
    'IE': EircodeField,
    'IL': ILPostalCodeField,
    'IN': INZipCodeField,
    'IR': IRPostalCodeField,
    'IT': ITZipCodeField,
    'JP': JPPostalCodeField,
    'LT': LTPostalCodeField,
    'LV': LVPostalCodeField,
    'MA': MAPostalCodeField,
    'MT': MTPostalCodeField,
    'MX': MXZipCodeField,
    'NL': NLZipCodeField,
    'NO': NOZipCodeField,
    'NZ': NZPostCodeField,
    'PK': PKPostCodeField,
    'PL': PLPostalCodeField,
    'PT': PTZipCodeField,
    'RO': ROPostalCodeField,
    'RU': RUPostalCodeField,
    'SE': SEPostalCodeField,
    'SG': SGPostCodeField,
    'SK': SKPostalCodeField,
    'TR': TRPostalCodeField,
    'UA': UAPostalCodeField,
    'US': USZipCodeField,
    'ZA': ZAPostCodeField,
}


def _generate_class_from_zipcode_field(field_class):
    class _GeneratedValidator(BaseValidator):
        def validate_zipcode(self, value):
            return field_class().clean(value)
    return _GeneratedValidator


for cc, field_class in _zip_code_fields.items():
    register_validator_for(cc)(_generate_class_from_zipcode_field(field_class))


@register_validator_for('IS')
class ISValidator(BaseValidator):
    def validate_zipcode(self, value):
        if value not in [entry[0] for entry in IS_POSTALCODES]:
            raise ValidationError(_('Enter a postal code in the format XXX.'), code='invalid')
        return value


@register_validator_for('SI')
class SIValidator(BaseValidator):
    def validate_zipcode(self, value):
        try:
            if int(value) not in [entry[0] for entry in SI_POSTALCODES]:
                raise ValidationError(_('Enter a postal code in the format XXXX.'), code='invalid')
        except ValueError:
            raise ValidationError(_('Enter a postal code in the format XXXX.'), code='invalid')
        return value
