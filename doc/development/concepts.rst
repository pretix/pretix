Implementation concepts
=======================

Basic terminology
-----------------

The components
^^^^^^^^^^^^^^

The project pretix is split into several components. The main three of them are:

**pretixbase**
    Tixlbase is the foundation below all other components. It is primarily
    responsible for the data structures and database communication. It also hosts
    several utilities which are used by multiple other components.

**pretixcontrol**
    Tixlcontrol is the web-based backend software which allows organizers to
    create and manage their events, items, orders and tickets.

**pretixpresale**
    Tixlpresale is the ticket-shop itself, containing all the parts visible to the
    end user.

Users and events
^^^^^^^^^^^^^^^^

Tixl is all about **events**, which are defined as something happening somewhere. 
Every Event is managed by the **organizer**, an abstract entity running the event.

Tixl is used by **users**. We want to enable global users who can just login into 
pretix and buy tickets for as many events as they like but at the same time it
should be possible to create some kind of local user to have a temporary account
just to buy tickets for one single event.

The problem is, we cannot use usernames as primary keys for our users, as we
do not want one username to be blocked forever just because of one temporary
account using it (people would have to think of a new username for every temporary
account they create). On the other hand, we can not use e-mail addresses either,
as those are not unique (imagine one person having multiple temporary accounts)
and they should not be required for temporary account (to enable anonymity).

Therefore, we split our users into two groups and use an internal **identifier**
as our primary key:

**Local users**
    Local users do only exist inside the scope of one event. They are identified by 
    usernames, which are only valid for exactly one event. Internally, their identifier 
    is "{username}@{event.id}.event.pretix"

**Global users**
    Global users exist everywhere in the installation of Tixl. They can buy tickets 
    for multiple events and they can be managers of one or more Organizers/Events. 
    Global users are identified by e-mail addresses.


Items and variations
^^^^^^^^^^^^^^^^^^^^

The purpose of pretix is to sell **items** (which belong to **events**) to **users**. 
An **item** is a abstract thing, popular examples being event tickets or a piece of 
merchandise, like 'T-Shirt'. An **item** can have multiple **properties** with multiple 
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

.. _restrictionconcept:

Restrictions
^^^^^^^^^^^^

The probably most powerful concepts of pretix is the very abstract concept of **restricitons**. 
We already know that **items** can come in very different **variations**, but a 
**restriction** decides whether an variation is available for sale and assign **prices** 
to **variations**. There are **restriction types** (pieces of code implementing the 
restriction logic) and **restriction instances** (the specific configurations made by the 
organzier). Although **restrictions** are a very abstract concept which can be used 
to do nearly anything, there are a few obvious examples:

* One easy example is a restriction by time, which allows the sale of certain item variations 
  only within a certain time frame. As restrictions can also assign a price to a variation, 
  this can also be used to implement something like 'early-bird prices' for your tickets by 
  using multiple time restrictions with different prices.
* The most obvious example is the restriction by number, which limits the sale of the tickets to 
  a maximum number. You can use this either to stop selling tickets completely when your house
  is full or for creating limited 'VIP tickets'. We'll come to this again later.
* A more advanced example is a restriction by user, for example reduced ticket prices for 
  users who are members of a special group.
* Arbitrary sophisticated features like coupon codes can also be implemented using 
  this feature.

Any number of **restrictions** can be applied to the whole of a **item** or even to a specific 
**variation**. The processing of the restriction follows the following set of rules:

* Variation-specific rules have precedence over item-specific rules.
* The restrictions are being processed in random order (there may not be any assumptions about 
  the evaluation order).
* Multiple restriction instances of **different restriction types** are linked with *and*, so 
  if both a time frame and a restriction by number are applied to an item, the item is only avaliable 
  for sale during the given time frame *and* only as long as items are available.
* Multiple restriction instances of the **same restriction type** are typically linked with *or*, 
  although this is the decision of the restriction logic itself and not mandatory. So for example
  the restriction by time would implement this default logic, because if two time frames are applied 
  to an item, the item should be available for sale in both of the time frames (it just does not make
  sense otherwise on an one-dimensional time axis).
* If multiple restrictions apply which set the price, the *cheapest* price determines the final price.

Restrictions can be implemented using a plugin system and do not require changes to the pretix codebase.

Restriction by number
"""""""""""""""""""""

The restriction by number is a special case, as it is the only (planned) restriction type demanding
special care in the implementation to never sell more tickets than allowed, even under heavy load.

* There is a concept of **quotas**. A quota is basically a number of items combined with information
  about how many of them are still available.
* Every time a user places a item in the cart, a **cart lock** is created, reducing the number of
  available items in the pool by one. The lock is valid for a fixed time (e.g. 30 minutes), but not
  instantly deleted afther those 30 minutes (we'll get to that).
* Every time a user places a binding order, the lock object is replaced by an **order** which behaves
  much the same as the lock. It reduces the number of available item and is valid for a fixed time, this
  time for the configured payment term (e.g. 14 days).
* If the order is being paid, the **order** becomes permanent.
* Once there are no available tickets left and user A wants to buy a ticket, he can do so, as long as 
  there are *expired* cart locks in the system. In this case, user A gets a new cart lock, so that there 
  are  more cart locks than available tickets and therefore have to remove one of the expired cart locks.
  However, we do not choose one by random, but keep the surplus in a way that leads to the deletion
  of the cart lock of the user who tries *last* to use his lock.
* The same goes for orders which are not paid within the specified timeframe. This policy allows to
  sell as much items as possible, guarantees you to get your item if you checkout within the validity 
  period of your lock or pay within the validity period of your order. It does not guarantee you anything
  any longer, but it tries to be *as tolerant as possible* to users who are paying after their payment
  period or click checkout after the expiry of their lock.
* The same quota can apply to multiple items and one item can be affected by multiple quotas
