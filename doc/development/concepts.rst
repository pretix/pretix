Implementation concepts
=======================

Basic terminology
-----------------

The components
^^^^^^^^^^^^^^

The project pretix is split into several components. The main three of them are:

**pretix.base**
    Pretixbase is the foundation below all other components. It is primarily
    responsible for the data structures and database communication. It also hosts
    several utilities which are used by multiple other components.

**pretix.control**
    Pretixcontrol is the web-based backend software which allows organizers to
    create and manage their events, items, orders and tickets.

**pretix.presale**
    Pretixpresale is the ticket-shop itself, containing all the parts visible to the
    end user.

Users and events
^^^^^^^^^^^^^^^^

Pretix is all about **events**, which are defined as something happening somewhere.
Every event is managed by the **organizer**, an abstract entity running the event.

Pretix has a concept of **users** that is used for all the people who have to log
in to the control panel to manage one or more events. No user is required to place an
order.


Items and variations
^^^^^^^^^^^^^^^^^^^^

The purpose of pretix is to sell **items** (which belong to **events**) to **users**. 
An **item** is a abstract thing, popular examples being event tickets or a piece of 
merchandise, like 'T-shirt'. An **item** can have multiple **properties** with multiple 
**values** each. For example, the **item** 'T-Shirt' could have the **property** 'Size' 
with **values** 'S', 'M' and 'L' and the **property** 'Color' with **values** 'black' 
and 'blue'.

Any combination of those **values** is called a **variation**. Using the examples from 
above, a possible **variation** would be 'T-Shirt, S, blue'.

Questions
^^^^^^^^^

An item can be extended using **questions**. Questions enable items to be extended by
additional information which can be entered by the user. Examples of possible questions
include 'Name' or 'age'.

Restriction by number
"""""""""""""""""""""

The restriction by number is a special case, as it is the only (planned) restriction type demanding
special care in the implementation to never sell more tickets than allowed, even under heavy load.

* There is a concept of **quotas**. A quota is basically a number of items combined with information
  about how many of them are still available.
* Every time a user places a item in the cart, a **cart lock** is created, reducing the number of
  available items in the pool by one. The lock is valid for a fixed time (e.g. 30 minutes), but not
  instantly deleted after those 30 minutes (we'll get to that).
* Every time a user places a binding order, the lock object is replaced by an **order** which behaves
  much the same as the lock. It reduces the number of available item and is valid for a fixed time, this
  time for the configured payment term (e.g. 14 days).
* If the order is being paid, the **order** becomes permanent.
* Once there are no available tickets left and user A wants to buy a ticket, he can do so, as long as 
  there are *expired* cart locks in the system. In this case, user A gets a new cart lock, so that there 
  are  more cart locks than available tickets and therefore have to remove one of the expired cart locks.
  However, we do not choose one by random, but keep the surplus in a way that leads to the deletion
  of the cart lock of the user who tries *last* to use his lock.
* The same goes for orders which are not paid within the specified timeframe. This policy allows the organizer to
  sell as much items as possible. Moreover, it guarantees the users to get their items if they check out within the validity 
  period of their locks and pay within the validity period of their orders. It does not guarantee them anything
  any longer, but it tries to be *as tolerant as possible* to users who are paying after their payment
  period or click checkout after the expiry of their lock.
* The same quota can apply to multiple items and one item can be affected by multiple quotas.

