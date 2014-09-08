Development goals
=================

Tixl is a web software handling presale of event tickets.

Technical goals
---------------

* Python 3.4 features may be used, Python 3.2 is an absolute requirement
* Use Django 1.7+
* Be PEP-8 compliant
* Be fully internationalization, unicode and timezone aware
* Use a fully documented and reproducible setup
* Be fully tested by both unit and behaviour tests
* Use LessCSS

Feature goals
-------------

* One tixl software installation has to cope with multiple events by multiple organizers
* There is no code access necessary to create a new event
* Tixl is abstract in many ways to adopt to as much events as possible.

    * Tickets are only an instance of an abstract model called items, such that the system can also sell e.g. merchandise
    * An abstract concept of restriction is used to restrict the selling of tickets, for example by date, by number or by user permissions.
    * Items can come in multiple flavors (like t-shirt sizes or colors)
    * Items can require additional user input (like attendee names)

* The software is not only user, but also admin-friendly and provides a beautiful and time-saving interface for all admin jobs
* The software is able to import bank data, at least using CSV files with support for MT940 or later even HBCI
* There is the possibility to add more payment methods later, such as credit card payment, PayPal or even cash
* There is a flexible concept of payment goals which works well together with the restriction framework mentioned above
* There is the possibility to send out payment reminders
* There is the possibility to cancel orders
* There is the possibility of one user submitting multiple orders
* The user can download the ticket in PDF form, for which the admin can upload and customize a template without ever touching a line of code
* The system provides a variety of statistics
* The system provices export methods for multiple cashdesk/ticket validation systems
