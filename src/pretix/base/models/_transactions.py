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

"""
This module contains helper functions that are supposed to call out code paths missing calls to
``Order.create_transaction()`` by actively breaking them. Read the docstring of the ``Transaction`` class for a
detailed reasoning why this exists.
"""
import inspect
import logging
import os
import threading

from django.conf import settings
from django.db import transaction

dirty_transactions = threading.local()

logger = logging.getLogger(__name__)
fail_loudly = os.getenv('PRETIX_DIRTY_TRANSACTIONS_QUIET', 'false' if settings.DEBUG else 'true') not in ('true', 'True', 'on', '1')


class DirtyTransactionsForOrderException(Exception):
    pass


def _fail(message):
    if fail_loudly:
        raise DirtyTransactionsForOrderException(message)
    else:
        if settings.SENTRY_ENABLED:
            import sentry_sdk

            sentry_sdk.capture_message(message, "fatal")

        logger.warning(message, stack_info=True)


def _check_for_dirty_orders():
    if getattr(dirty_transactions, 'order_ids', None) is None:
        dirty_transactions.order_ids = set()
    try:
        if dirty_transactions.order_ids and dirty_transactions.order_ids != {None}:
            _fail(
                f"In the transaction that just ended, you created or modified an Order, OrderPosition, or OrderFee "
                f"object in a way that you should have called `order.create_transactions()` afterwards. The transaction "
                f"still went through and your data can be fixed with the `create_order_transactions` management command "
                f"but you should update your code to prevent this from happening. Affected order IDs: {dirty_transactions.order_ids}"
            )
    finally:
        dirty_transactions.order_ids.clear()


def _transactions_mark_order_dirty(order_id, using=None):
    if "PYTEST_CURRENT_TEST" in os.environ:
        # We don't care about Order.objects.create() calls in test code so let's try to figure out if this is test code
        # or not.
        for frame in inspect.stack():
            if 'pretix/base/models/orders' in frame.filename:
                continue
            elif 'test_' in frame.filename or 'conftest.py in frame.filename':
                return
            elif 'pretix/' in frame.filename or 'pretix_' in frame.filename:
                # This went through non-test code, let's consider it non-test
                break

    if order_id is None:
        return

    conn = transaction.get_connection(using)
    if not conn.in_atomic_block:
        _fail(
            "You modified an Order, OrderPosition, or OrderFee object in a way that should create "
            "a new Transaction object within the same database transaction, however you are not "
            "doing it inside a database transaction!"
        )

    if getattr(dirty_transactions, 'order_ids', None) is None:
        dirty_transactions.order_ids = set()

    if _check_for_dirty_orders not in [func for savepoint_id, func in conn.run_on_commit]:
        transaction.on_commit(_check_for_dirty_orders, using)
        dirty_transactions.order_ids.clear()  # This is necessary to clean up after old threads with rollbacked transactions

    dirty_transactions.order_ids.add(order_id)


def _transactions_mark_order_clean(order_id):
    if getattr(dirty_transactions, 'order_ids', None) is None:
        dirty_transactions.order_ids = set()
    try:
        dirty_transactions.order_ids.remove(order_id)
    except KeyError:
        pass
