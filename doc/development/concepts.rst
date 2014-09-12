Implementation Concepts
=======================

Basic terminology
-----------------

Users and events
^^^^^^^^^^^^^^^^

Tixl is all about **events**, which are defined as something happening somewhere. Every Event is managed by the **organizer**, an abstract entity running the event.

Tixl is used by **users**, of which it knows two types:

**Local users**
    Local users do only exist inside the scope of one event. They are identified by usernames, which are only valid for exactly one event.

**Global users**
    Global users exist everywhere in the installation of Tixl. They can buy tickets for multiple events and they can be managers of one or more Organizers/Events. Global users are identified by e-mail addresses.

For more information about this user concept and reasons behind it, see the docstring of the ``tixlbase.models.User`` class.

Items and flavors
^^^^^^^^^^^^^^^^^

The purpose of tixl is to sell **items** (which belong to **events**) to **users**. An **item** is a abstract thing, popular examples being event tickets or a piece of merchandise, like 'T-Shirt'. An **item** can have multiple **properties** with multiple **values** each. For example, the **item** 'T-Shirt' could have the **property** 'Size' with **values** 'S', 'M' and 'L' and the **property** 'Color' with **values** 'black' and 'blue'.

Any combination of those **values** is called a **flavor**. Using the examples from above, a possible **flavor** would be 'T-Shirt S blue'.

Restrictions
^^^^^^^^^^^^

The probably most powerful concepts of tixl is the very abstract concept of **restricitons**. We already know that **items** can come in very different **flavors**, but a **restriction** decides whether an item is available for sale and assign **prices** to **flavors**. There are **restriction types**, which are pieces of code implementing the restrictions and **restriction instances**, which are configurations made by the **organzier**. Although **restrictions** are a very abstract concept which can be used to do nearly anything, there are a few obvious examples:

* One easy example is the time restriction, which allows the sale of certain item flavors only within a certain time frame. As restrictions can also assign a price to a flavor, this can also be used to implement something like 'early-bird prices' for your tickets by using multiple time restrictions with different prices.
* The most obvious example is the number restriction, which limits the sale of the tickets to a maximum number. You can use this either to stop selling tickets completely when your house is full or for creating limited 'VIP tickets'.
* A more advanced example is a restriction by user, for example reduced ticket prices for members who are members of a special group.
* Arbitrary sophisticated features like coupon codes are also possible to be implemented using this feature.

Any number of **restrictions** can be applied to the whole of a **item** or to a specific **flavor**. The processing of the restriction follows the following set of rules:

* **Flavor**-specific rules have precedence over **item**-specific rules.
* The restrictions are being processed in random order (there may not be any assumptions about the evaluation order).
* Multiple restriction instances of **different restriction types** are linked with *and*, so if both a time frame and a number restriction are applied to an item, the item is only avaliable for sale within the given time frame *and* only as long as items are available.
* Multiple restriction instances of the **same restriction type** are linked with *or*, so if two time frames are applied to an item, the item is available for sale in both of the time frames. (This behaviour is actually a decision of the restriction type itself, so this rule is not enforced but rather a general rule of thumb). 
* If multiple restrictions apply which set the price, the *cheapest* price determines the final price.

Restriction types can be introduced by 3rd-party code and do not require changes to the tixl codebase.

.. note:: This pluggability of restrictions is implemented using the 'signal and receiver' pattern provided by Django. Restrictions can therefore live in seperate Django apps.
