#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013, Cédric Krier
# Copyright (c) 2014-2015, Nicolas Évrard
# Copyright (c) 2013-2015, B2CK
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the <organization> nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""a parser for MT940 files
"""
__version__ = '0.2'
__all__ = ['MT940', 'rabo_description', 'abn_amro_description',
           'ing_description']

from collections import namedtuple, defaultdict
from decimal import Decimal
import datetime
import re


SECTIONS = {
    'begin': [':940:'],
    'statement': [':20:'],
    'account': [':25:'],
    'information': [':28:', ':28C:'],
    'start_balance': [':60F:'],
    'transaction': [':61:'],
    'description': [':86:'],
    'end_balance': [':62F:'],
    }


def _parse_date(date):
    return datetime.datetime.strptime(date, '%y%m%d').date()


def _parse_amount(amount, sign='C'):
    amount = Decimal(amount.replace(',', '.'))
    if sign in ('D', 'RC'):
        return -amount
    return amount

TRANSACTION_RE = re.compile(r"""
    (?P<date>\d{6})
    (?P<booking>\d{4})?
    (?P<sign>D|C|RC|RD)
    (?P<code>\w)??  # ING skips this mandatory field
    (?P<amount>(\d|,){1,15})
    (?P<id>\w{4})
    (?P<reference>.{0,34})""", re.VERBOSE)


class MT940(object):

    def __init__(self, name):
        self.statements = []

        with open(name, 'rU') as f:
            values = defaultdict(str)
            transactions = []
            for line in self._readline(f):
                for name, sections in SECTIONS.iteritems():
                    if name == 'begin':
                        continue
                    for section in sections:
                        if line.startswith(section):
                            if name in values and name == 'statement':
                                self._set_statement(values, transactions)
                            if name.endswith('_balance'):
                                values[name] = self._get_balance(
                                    line[len(section):])
                            elif name == 'transaction':
                                transactions.append(
                                    self._get_transaction(line[len(section):]))
                            elif name == 'description':
                                transactions[-1] = (transactions[-1][:-1]
                                    + (line[len(section):],))
                            else:
                                values[name] += line[len(section):]
            if values:
                self._set_statement(values, transactions)

    @staticmethod
    def _readline(f):
        buf = []
        for line in f:
            line = line.strip('\n')
            if buf:
                if (line.startswith(':')
                        or line.startswith('-')):
                    yield '\n'.join(buf)
                    del buf[:]
            buf.append(line)
        if buf:
            yield '\n'.join(buf)

    @staticmethod
    def _get_balance(balance):
        date = _parse_date(balance[1:7])
        amount = _parse_amount(balance[10:], balance[0])
        return Balance(date=date, amount=amount, currency=balance[7:10])

    @staticmethod
    def _get_transaction(transaction):
        lines = transaction.splitlines()
        if len(lines) == 1:
            transaction, = lines
            additional_data = None
        else:
            transaction, additional_data = lines
        transaction = TRANSACTION_RE.match(transaction)
        date = _parse_date(transaction.group('date'))
        if transaction.group('booking'):
            booking = _parse_date(
                transaction.group('date')[:2]
                + transaction.group('booking'))
        else:
            booking = None
        amount = _parse_amount(transaction.group('amount'),
            transaction.group('sign'))
        id_ = transaction.group('id')
        reference = transaction.group('reference')
        reference, _, institution_reference = reference.partition('//')
        return (date, booking, amount, id_, reference,
            institution_reference, additional_data, '')

    def _set_statement(self, values, transactions):
        self.statements.append(
            Statement(
                transactions=[Transaction(*t) for t in transactions],
                **values))
        values.clear()
        del transactions[:]

Statement = namedtuple('Statement', ['statement', 'account', 'information',
        'start_balance', 'transactions', 'end_balance'])
Balance = namedtuple('Balance', ['date', 'amount', 'currency'])
Transaction = namedtuple('Transaction', ['date', 'booking', 'amount', 'id',
        'reference', 'institution_reference', 'additional_data',
        'description'])


def _find_swift_tags(tags, description):
    values = {}
    for tag, name in tags:
        if description.startswith(tag):
            description = description[len(tag):]
            try:
                i = description.index('/')
            except ValueError:
                i = len(description)
            values[name] = description[:i]
            description = description[i:]
        if not description:
            break
    return values

RABO_TAGS = [
    ('/MARF/', 'marf'),
    ('/EREF/', 'eref'),
    ('/PREF/', 'pref'),
    ('/BENM/', 'benm'),
    ('/ORDP/', 'ordp'),
    ('/NAME/', 'name'),
    ('/ID/', 'id'),
    ('/ADDR/', 'addr'),
    ('/REMI/', 'remi'),
    ('/CDTRREFTP//CD/SCOR/ISSR/CUR/CDTRREF/', 'cdtrref'),
    ('/CSID/', 'csid'),
    ('/ISDT/', 'isdt'),
    ('/RTRN/', 'rtrn'),
    ]


def rabo_description(description):
    "Return dictionnary with Rabo informations"
    description = ''.join(description.splitlines())
    return _find_swift_tags(RABO_TAGS, description)


ABN_AMRO_ACCOUNT = re.compile(r"""
    ^([0-9]{1,3}\.[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3})""", re.VERBOSE)
ABN_AMRO_GIRO = re.compile(r"""
    ^GIRO\ +([0-9]+)""", re.VERBOSE)
ABN_AMRO_TAGS = [
    ('/TRTP/', 'trtp'),
    ('/IBAN/', 'iban'),
    ('/BIC/', 'bic'),
    ('/CSID', 'csid'),
    ('/NAME/', 'name'),
    ('/REMI/', 'remi'),
    ('/EREF/', 'eref'),
    ('/ORDP//ID/', 'ordp'),
    ('/BENM//ID/', 'benm'),
    ]


def abn_amro_description(description):
    "Retrun dictionnary with ABN AMRO informations"
    description = ''.join(description.splitlines())
    values = {}
    m = ABN_AMRO_ACCOUNT.match(description)
    if m:
        values['account'] = m.group(1).replace('.', '')
    m = ABN_AMRO_GIRO.match(description)
    if m:
        values['account'] = m.group(1)
    values.update(_find_swift_tags(ABN_AMRO_TAGS, description))
    return values

ING_TAGS = re.compile(r'/(RTRN|EREF|PREF|MARF|CSID|CNTP|REMI|PURP|ULT[CD])/')
ING_TAGS_DEFINITION = {
    'RTRN': ('rtrn', []),
    'EREF': ('eref', []),
    'PREF': ('pref', []),
    'MARF': ('marf', []),
    'CSID': ('csid', []),
    'CNTP': ('cntp', ['account_number', 'bic', 'name', 'city']),
    'REMI': ('remi', ['code', 'issuer', 'remittance_info']),
    'PURP': ('purp', []),
    'ULTC': ('ultc', ['name', 'id']),
    'ULTD': ('ultd', ['name', 'id']),
    }


def ing_description(description):
    "Return dictionnary with ING informations"
    description = ''.join(description.splitlines())
    values = {}
    ing_tags = iter(ING_TAGS.split(description)[1:])
    for tag, tag_value in zip(ing_tags, ing_tags):
        tag_value = tag_value[:-1]
        name, subfields = ING_TAGS_DEFINITION[tag]

        if not subfields:
            values[name] = tag_value
            continue

        values[name] = {}
        if 'name' in subfields or 'remittance_info' in subfields:
            special_tag = 'name' if 'name' in subfields else 'remittance_info'
            tag_idx = subfields.index(special_tag)
            subtags = tag_value.split('/', tag_idx)
            for sf_name, sf_value in zip(subfields[:tag_idx], subtags[:-1]):
                values[name][sf_name] = sf_value
            subtags = subtags[-1].rsplit('/', len(subfields) - tag_idx - 1)
            for sf_name, sf_value in zip(subfields[tag_idx:], subtags):
                values[name][sf_name] = sf_value
        else:
            subtags = tag_value.split('/')
            for sf_name, sf_value in zip(subfields, subtags):
                values[name][sf_name] = sf_value

    return values
