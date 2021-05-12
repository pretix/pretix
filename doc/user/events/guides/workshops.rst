Use case: Conference with workshops
-----------------------------------

When running a conference, you might also organize a number of workshops with smaller capacity. To be able to plan, it would be great to know which workshops an attendee plans to attend.

Option A: Questions
"""""""""""""""""""

Your first and simplest option is to just create a multiple-choice question. This has the upside of making it easy for users to change their mind later on, but will not allow you to restrict the number of attendees signing up for a given workshop – or even charge extra for a given workshop.

Option B: Add-on products with fixed time slots
"""""""""""""""""""""""""""""""""""""""""""""""

The usually better option is to go with add-on products. Let's take for example the following conference schedule, in which the lecture can be attended by anyone, but the workshops only have space for 20 persons each:

==================== =================================== ===================================
Time                 Room A                              Room B
==================== =================================== ===================================
Wednesday morning    Lecture
Wednesday afternoon  Workshop A                          Workshop B
Thursday morning     Workshop C                          Workshop D (20 € extra charge)
==================== =================================== ===================================

Assuming you already created one or more products for your general conference admission, we suggest that you additionally create:

* A category called "Workshops" with the checkbox "Products in this category are add-on products" activated

* A free product called "Wednesday afternoon" within the category "Workshops" and with two variations:

    * Workshop A

    * Workshop B

* A free product called "Thursday morning" within the category "Workshops" and with two variations:

    * Workshop C

    * Workshop D with a price of 20 €

* Four quotas for each of the workshops

* One add-on configuration on your base product that allows users to choose between 0 and 2 products from the category "Workshops"

Option C: Add-on products with variable time slots
""""""""""""""""""""""""""""""""""""""""""""""""""

The above option only works if your conference uses fixed time slots and every workshop uses exactly one time slot. If
your schedule looks like this, it's not going to work great:

+-------------+------------+-----------+
| Time        | Room A     | Room B    |
+=============+============+===========+
| 09:00-11:00 | Talk 1     | Long      |
+-------------+------------+ Workshop 1|
| 11:00-13:00 | Talk 2     |           |
+-------------+------------+-----------+
| 14:00-16:00 | Long       | Talk 3    |
+-------------+ workshop 2 +-----------+
| 16:00-18:00 |            | Talk 4    |
+-------------+------------+-----------+

In this case, we recommend that you go to *Settings*, then *Plugins* and activate the plugin **Agenda constraints**.

Then, create a product (without variations) for every single part that should be bookable (talks 1-4 and long workshops
1 and 2) as well as appropriate quotas for each of them.

All of these products should be part of the same category. In your base product (e.g. your conference ticket), you
can then create an add-on product configuration allowing users to add products from this category.

If you edit these products, you will be able to enter the "Start date" and "End date" of the talk or workshop close
to the bottom of the page. If you fill in these values, pretix will automatically ensure no overlapping talks are
booked.

.. note::

    This option is currently only available on pretix Hosted. If you are interested in using it with pretix Enterprise,
    please contact sales@pretix.eu.
