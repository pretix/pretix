.. highlight:: python

Resource locking
================

.. versionchanged:: 2023.8

   Our locking mechanism changed heavily in version 2023.8. Read `this PR`_ for background information.

One of pretix's core objectives as a ticketing system could be described as the management of scarce resources.
Specifically, the following types of scarce-ness exist in pretix:

- Quotas can limit the number of tickets available
- Seats can only be booked once
- Vouchers can only be used a limited number of times
- Some memberships can only be used a limited number of times

For all of these, it is critical that we prevent race conditions.
While for some events it wouldn't be a big deal to sell a ticket more or less, for some it would be problematic and selling the same seat twice would always be catastrophic.

We therefore implement a standardized locking approach across the system to limit concurrency in cases where it could
be problematic.

To acquire a lock on a set of quotas to create a new order that uses that quota, you should follow the following pattern::

    with transaction.atomic(durable=True):
        quotas = Quota.objects.filter(...)
        lock_objects(quotas, shared_lock_objects=[event])
        check_quota(quotas)
        create_ticket()

The lock will automatically be released at the end of your database transaction.

Generally, follow the following guidelines during your development:

- **Always** acquire a lock on every **quota**, **voucher** or **seat** that you "use" during your transaction. "Use"
  here means any action after which the quota, voucher or seat will be **less available**, such as creating a cart
  position, creating an order, creating a blocking voucher, etc.

  - There is **no need** to acquire a lock if you **free up** capacity, e.g. by canceling an order, deleting a voucher, etc.

- **Always** acquire a shared lock on the ``event`` you are working in whenever you acquire a lock on a quota, voucher,
  or seat.

- Only call ``lock_objects`` **once** per transaction. If you violate this rule, `deadlocks`_ become possible.

- For best performance, call ``lock_objects`` as **late** in your transaction as possible, but always before you check
  if the desired resource is still available in sufficient quantity.

Behind the scenes, the locking is implemented through `PostgreSQL advisory locks`_. You should also be aware of the following
properties of our system:

- In some situations, an exclusive lock on the ``event`` is used, such as when the system can't determine for sure which
  seats will become unavailable after the transaction.

- An exclusive lock on the event is also used if you pass more than 20 objects to ``lock_objects``. This is a performance
  trade-off because it would take long to acquire all of the individual locks.

- If ``lock_objects`` is unable to acquire a lock within 3 seconds, a ``LockTimeoutException`` will be thrown.

.. note::

   We currently do not use ``lock_objects`` for memberships. Instead, we use ``select_for_update()`` on the membership
   model. This might change in the future, but you should usually not be concerned about it since
   ``validate_memberships_in_order(lock=True)`` will handle it for you.

.. _this PR: https://github.com/pretix/pretix/pull/2408
.. _deadlocks: https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS
.. _PostgreSQL advisory locks: https://www.postgresql.org/docs/11/explicit-locking.html#ADVISORY-LOCKS