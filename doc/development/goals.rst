Development goals
=================

Pretix is a web software handling presale of event tickets.

Technical goals
---------------

* Python 3.4
* Use Django 1.8+
* Be [PEP-8](https://www.python.org/dev/peps/pep-0008/) compliant
* Be fully internationalized, unicode and timezone aware
* Use a fully documented and reproducible setup
* Be fully tested by unit tests
* Use LessCSS

Feature goals
-------------

Next goals
^^^^^^^^^^
* HBCI support
* There is the possibility to send out payment reminders
* The user can download the ticket in PDF form, for which the organizer can upload and customize a template without ever touching a line of code
* The system provides a variety of statistics
* The system provides export methods for multiple cashdesk/ticket validation systems

Achieved goals
^^^^^^^^^^^^^^
* One pretix software installation has to cope with multiple events by multiple organizers
* There is no code access necessary to create a new event
* Pretix is abstract in many ways to adopt to as much events as possible.

    * Tickets are only an instance of an abstract model called items, such that the system can also sell e.g. merchandise
    * An abstract concept of restriction is used to restrict the selling of tickets, for example by date, by number or by user permissions.
    * Items can come in multiple flavors (like T-shirt sizes or colors)
    * Items can require additional user input (like attendee names)

* The software is not only user-, but also organizer- and admin-friendly and provides a beautiful and time-saving interface for all admin jobs
* The software is able to import bank data, at least using CSV files with support for MT940
* There is the possibility to add more payment methods later, such as credit card payment, PayPal or even cash
* There is a flexible concept of payment goals which works well together with the restriction framework mentioned above
* There is the possibility to cancel orders
* There is the possibility of one user submitting multiple orders
