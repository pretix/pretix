.. _seasontickets:

Use case: Season tickets
========================

Season tickets and similar time-based tickets are popular for swimming pools, sports clubs, theaters and lots of other
types of venues. In this article, we show you different ways to set them up with pretix.  Of course, other types of
tickets such as week tickets, month tickets or tickets of ten can be created with the same mechanism.

There is a big difference between the two ways we show below.

With **Option A**, a customer who purchases a season ticket creates an account with their email address and a password
and the season ticket will be saved in that account. If the customer wants to use the season ticket, they need to buy
an additional free ticket for the specific event they want to visit. This makes sense for all events or venues with
**limited capacity** or **reserved seating**, because it still allows you to set an upper limit of people showing up
for a specific event or time slot.

With **Option B**, a customer who purchases a season ticket receives a single ticket with a single QR code that can be
used an unlimited number of times. This makes sense if the capacity of your venue is virtually unlimited and you do not
need to know in advance how many season ticket holders will show up.

Option A: Memberships and multiple tickets
""""""""""""""""""""""""""""""""""""""""""

Since this approach requires customers to be identified with a customer account, you first need to enable the customer
accounts feature in your organizer settings in the "Customer accounts" tab.

.. thumbnail:: ../../../screens/event/seasontickets_orgsettings.png
   :align: center
   :class: screenshot

After doing so, a new menu item "Customer accounts" will also show up in the main menu of your organizer account on
the left. Open it's menu and click on "Membership types". Then, select to "create a new membership type".

You can name the membership type in a way that clearly explains where it is valid, e.g. "season pass main location"
or "season pass all locations". There are a few details you can configure on this page, such as whether the season pass
can be used by multiple different persons, or if the season pass can be used for multiple tickets for the same time
slot. You can also define a maximum number of usages, which is useful if you e.g. use this feature to add a "ticket of
ten".

.. thumbnail:: ../../../screens/event/seasontickets_membershiptype.png
   :align: center
   :class: screenshot

Next, you need a way of selling these season passes. Theoretically this can be done through the same event series that
you usually use, but it's probably cleaner and easier to find for customers if you create a **new event** that you only
use to sell season passes. The start and end date of the new event should correspond to the dates of your season.

Inside the new event, you only need to create a single product which you can call "season ticket". Inside that product's
settings, head to the "Additional settings" section and look for the option "This product creates a membership of type".
Select the membership type you just created. By default, the checkbox "The duration of the membership is the same as the
duration of the event or event series date" is active, which is fine for our season ticket example, but you might need
to unset it and provide custom timing for other ticket types such as week passes.

.. thumbnail:: ../../../screens/event/seasontickets_issue.png
   :align: center
   :class: screenshot

To prevent confusion, it might be useful to turn off ticket downloading at "Settings" → "Tickets" for your new event.
That's it, you are now ready to sell season tickets!

We can now deal with how to use the season tickets. Move back to your existing event and create a new product
**or** product variation of your regular product which you call "ticket for season ticket holders" and assign a price
of zero. In the "Availability" section of the product or variation settings, check the option "Require a valid
membership" and again select the membership type you created. You can of course repeat this with all events the season
ticket holder should have access to.

.. thumbnail:: ../../../screens/event/seasontickets_require.png
   :align: center
   :class: screenshot

Option B: All-access in a single pass
"""""""""""""""""""""""""""""""""""""

If you have only a single event series with many time slots and you do not care how many season ticket holders show up,
there's a solution that does not require your customers to set up accounts and book a new ticket on every visit.

Instead, you can just create an additional product "Season ticket" that you enable either in a "special" date of your
event series just created for this purpose, or in all of your dates so it can be easily found by customers.

Then, you can set up your check-in lists with custom logic in the "Advanced" tab of your check-in list settings.
The logic needs to ensure the following requirements:

* Regular ticket holders can only get in during their assigned time frame **and** when they haven't used their ticket before.

* Season ticket holders can always get in.

Here's an example on how to set this up:

.. thumbnail:: ../../../screens/event/seasontickets_rules.png
   :align: center
   :class: screenshot
