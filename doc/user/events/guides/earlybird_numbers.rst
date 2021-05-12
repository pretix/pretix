Use case: Early-bird tiers based on ticket numbers
--------------------------------------------------

Let's say you run a conference with 400 tickets that has the following pricing scheme:

* First 100 tickets ("super early bird"): € 450
* Next 100 tickets ("early bird"): € 550
* Remaining tickets ("regular"): € 650

First of all, create three products:

* "Super early bird ticket"
* "Early bird ticket"
* "Regular ticket"

Then, create three quotas:

* "Super early bird" with a **size of 100** and the "Super early bird ticket" product selected. At "Advanced options",
  select the box "Close this quota permanently once it is sold out".

* "Early bird and lower" with a **size of 200** and both of the "Super early bird ticket" and "Early bird ticket"
  products selected. At "Advanced options", select the box "Close this quota permanently once it is sold out".

* "All participants" with a **size of 400**, all three products selected and **no additional options**.

Next, modify the product "Regular ticket". In the section "Availability", you should look for the option "Only show
after sellout of" and select your quota "Early bird and lower". Do the same for the "Early bird ticket" with the quota
"Super early bird ticket".

This will ensure the following things:

* Each ticket level is only visible after the previous level is sold out.

* As soon as one level is really sold out, it's not coming back, because the quota "closes", i.e. locks in place.

* By creating a total quota of 400 with all tickets included, you can still make sure to sell the maximum number of
  tickets, even if e.g. early-bird tickets are canceled.

Optionally, if you want to hide the early bird prices once they are sold out, go to "Settings", then "Display" and
select "Hide all products that are sold out". Of course, it might be a nice idea to keep showing the prices to remind
people to buy earlier next time ;)

Please note that there might be short time intervals where the prices switch back and forth: When the last early bird
tickets are in someone's cart (but not yet sold!), the early bird tickets will show as "Reserved" and the regular
tickets start showing up. However, if the customers holding the reservations do not complete their order,
the early bird tickets will become available again. This is not avoidable if we want to prevent malicious users
from blocking all the cheap tickets without an actual sale happening.
