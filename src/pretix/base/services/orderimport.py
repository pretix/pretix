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
import csv
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext as _

from pretix.base.i18n import LazyLocaleException, language
from pretix.base.models import (
    CachedFile, Event, InvoiceAddress, Order, OrderPayment, OrderPosition,
    User,
)
from pretix.base.models.orders import Transaction
from pretix.base.orderimport import get_all_columns
from pretix.base.services.invoices import generate_invoice, invoice_qualified
from pretix.base.services.tasks import ProfiledEventTask
from pretix.base.signals import order_paid, order_placed
from pretix.celery_app import app


class DataImportError(LazyLocaleException):
    def __init__(self, *args):
        msg = args[0]
        msgargs = args[1] if len(args) > 1 else None
        self.args = args
        if msgargs:
            msg = _(msg) % msgargs
        else:
            msg = _(msg)
        super().__init__(msg)


def parse_csv(file, length=None, mode="strict"):
    file.seek(0)
    data = file.read(length)
    try:
        import chardet
        charset = chardet.detect(data)['encoding']
    except ImportError:
        charset = file.charset
    data = data.decode(charset or "utf-8", mode)
    # If the file was modified on a Mac, it only contains \r as line breaks
    if '\r' in data and '\n' not in data:
        data = data.replace('\r', '\n')

    try:
        dialect = csv.Sniffer().sniff(data.split("\n")[0], delimiters=";,.#:")
    except csv.Error:
        return None

    if dialect is None:
        return None

    reader = csv.DictReader(io.StringIO(data), dialect=dialect)
    return reader


def setif(record, obj, attr, setting):
    if setting.startswith('csv:'):
        setattr(obj, attr, record[setting[4:]] or '')


@app.task(base=ProfiledEventTask, throws=(DataImportError,))
def import_orders(event: Event, fileid: str, settings: dict, locale: str, user) -> None:
    # TODO: quotacheck?
    cf = CachedFile.objects.get(id=fileid)
    user = User.objects.get(pk=user)
    with language(locale, event.settings.region):
        cols = get_all_columns(event)
        parsed = parse_csv(cf.file)
        orders = []
        order = None
        data = []

        # Run validation
        for i, record in enumerate(parsed):
            if not any(record.values()):
                continue
            values = {}
            for c in cols:
                val = c.resolve(settings, record)
                if isinstance(val, str):
                    val = val.strip()
                try:
                    values[c.identifier] = c.clean(val, values)
                except ValidationError as e:
                    raise DataImportError(
                        _(
                            'Error while importing value "{value}" for column "{column}" in line "{line}": {message}').format(
                            value=val if val is not None else '', column=c.verbose_name, line=i + 1, message=e.message
                        )
                    )
            data.append(values)

        # Prepare model objects. Yes, this might consume lots of RAM, but allows us to make the actual SQL transaction
        # shorter. We'll see what works better in reality…
        for i, record in enumerate(data):
            try:
                if order is None or settings['orders'] == 'many':
                    order = Order(
                        event=event,
                        testmode=settings['testmode'],
                    )
                    order.meta_info = {}
                    order._positions = []
                    order._address = InvoiceAddress()
                    order._address.name_parts = {'_scheme': event.settings.name_scheme}
                    orders.append(order)

                position = OrderPosition(positionid=len(order._positions) + 1)
                position.attendee_name_parts = {'_scheme': event.settings.name_scheme}
                position.meta_info = {}
                order._positions.append(position)
                position.assign_pseudonymization_id()

                for c in cols:
                    c.assign(record.get(c.identifier), order, position, order._address)

            except ImportError as e:
                raise ImportError(
                    _('Invalid data in row {row}: {message}').format(row=i, message=str(e))
                )

        # quota check?
        with event.lock():
            with transaction.atomic():
                save_transactions = []
                for o in orders:
                    o.total = sum([c.price for c in o._positions])  # currently no support for fees
                    if o.total == Decimal('0.00'):
                        o.status = Order.STATUS_PAID
                        o.save()
                        OrderPayment.objects.create(
                            local_id=1,
                            order=o,
                            amount=Decimal('0.00'),
                            provider='free',
                            info='{}',
                            payment_date=now(),
                            state=OrderPayment.PAYMENT_STATE_CONFIRMED
                        )
                    elif settings['status'] == 'paid':
                        o.status = Order.STATUS_PAID
                        o.save()
                        OrderPayment.objects.create(
                            local_id=1,
                            order=o,
                            amount=o.total,
                            provider='manual',
                            info='{}',
                            payment_date=now(),
                            state=OrderPayment.PAYMENT_STATE_CONFIRMED
                        )
                    else:
                        o.status = Order.STATUS_PENDING
                        o.save()
                    for p in o._positions:
                        p.order = o
                        p.save()
                    o._address.order = o
                    o._address.save()
                    for c in cols:
                        c.save(o)
                    o.log_action(
                        'pretix.event.order.placed',
                        user=user,
                        data={'source': 'import'}
                    )
                    save_transactions += o.create_transactions(is_new=True, fees=[], positions=o._positions, save=False)
                Transaction.objects.bulk_create(save_transactions)

            for o in orders:
                with language(o.locale, event.settings.region):
                    order_placed.send(event, order=o)
                    if o.status == Order.STATUS_PAID:
                        order_paid.send(event, order=o)

                    gen_invoice = invoice_qualified(o) and (
                        (event.settings.get('invoice_generate') == 'True') or
                        (event.settings.get('invoice_generate') == 'paid' and o.status == Order.STATUS_PAID)
                    ) and not o.invoices.last()
                    if gen_invoice:
                        generate_invoice(o, trigger_pdf=True)
    cf.delete()
