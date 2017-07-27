Sending Email
=============

pretix allows event organizers to configure how they want to send emails to their users in multiple ways.
Therefore, all emails should be sent through the following function.

If the email you send is related to an order, you should also take a look at the
:py:meth:`~pretix.base.models.Order.send_mail` of the order model.

.. autofunction:: pretix.base.services.mail.mail
