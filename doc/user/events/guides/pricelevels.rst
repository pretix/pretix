Use case: Multiple price levels
-------------------------------

Imagine you're running a concert with general admission that sells a total of 200 tickets for two prices:

* Regular: € 25.00
* Students: € 19.00

You can either set up two different products called e.g. "Regular ticket" and "Student ticket" with the respective prices, or two variations within the same product. In this simple case, it really doesn't matter.

In addition, you will need quotas. If you do not care how many of your tickets are sold to students, you should set up just **one quota** of 200 called e.g. "General admission" that you link to **both products**.

If you want to limit the number of student tickets to 50 to ensure a certain minimum revenue, but do not want to limit the number of regular tickets artificially, we suggest you to create the same quota of 200 that is linked to both products, and then create a **second quota** of 50 that is only linked to the student ticket. This way, the system will reduce both quotas whenever a student ticket is sold and only the larger quota when a regular ticket is sold.
