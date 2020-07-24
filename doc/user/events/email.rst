E-mail settings
===============

The settings at "Settings" → "E-mail" allow you to customize the emails that pretix sends to the participants of your
event.

.. thumbnail:: ../../screens/event/settings_email.png
   :align: center
   :class: screenshot

The page is separated into four parts: "E-mail settings", "E-mail design", "E-mail content" and "SMTP settings".
We will explain all of them in detail on this page.

E-mail settings
---------------

The upper part of the page contains settings that are relevant for the generation of all e-mails alike. Those are
currently:

Subject prefix
    This text will be prepended to the subject of all e-mails that are related to your event. For example, if you
    set this to "dc2018" all subjects will be formatted like "[dc2018] Your payment was successful".

Sender address
    All e-mails will be sent with this address in the "From" field. If you use an email address at a custom domain,
    we strongly recommend to use the SMTP settings below as well, otherwise your e-mails might be detected as spam
    due to the `Sender Policy Framework`_ and similar mechanisms.

Sender name
    This is the name associated with the sender address. By default, this is your event name.

Signature
    This text will be appended to all e-mails in form of a signature. This might be useful e.g. to add your contact
    details or any legal information that needs to be included with the e-mails.

Bcc address
    This email address will receive a copy of every event-related email.

Attach calender files
    With this option, every order confirmation mail will include an ics file with name, date and location of
    your event. It can be imported into many digital calendars.

Sales Channels for Checkout Emails
    When you are using multiple sales channel, you may want to decide that mails for order and payment confirmation
    are only to be sent for some sales channels. For orders created through the default online shop, these emails
    must always be send. A similar option is available for ticket download reminders.

E-mail design
-------------

In this part, you can choose and preview the layout of your emails. More layouts can be added by pretix plugins.

E-mail content
--------------

The next part of the page allows you to customize the exact texts of all e-mails sent by the system automatically.
You can click on the different boxes to expand them and see the texts.

Within the texts, you can use placeholders that will later by replaced by values depending on the event or order. Below
every text box is a list of supported placeholders, but currently the following are defined (not every placeholder
is valid in every text):

============================== ===============================================================================
Placeholder                    Description
============================== ===============================================================================
event                          The event name
total                          The order's total value
total_with_currency            The order's total value with a localized currency sign
currency                       The currency used for the event (three-letter code)
payment_info                   Information text specific to the payment method (e.g. banking details)
url                            An URL pointing to the download/status page of the order
invoice_name                   The name field of the invoice address
invoice_company                The company field of the invoice address
expire_date                    The order's expiration date
date                           The same as ``expire_date``, but in a different e-mail (for backwards
                               compatibility)
orders                         A list of orders including links to their status pages, specific to the "resend
                               link (requested by user)" e-mail
code                           In case of the waiting list, the voucher code to redeem
hours                          In case of the waiting list, the number of hours the voucher code is valid
============================== ===============================================================================

The different e-mails are explained in the following:

Placed Order
    This e-mail is sent out to every order directly after the order has been received, except if the order total
    is zero (see below). It should specify that/how the order is to be paid.

Paid Order
    This e-mail is sent out as soon as the payment for an order has been received and should give the customer
    more information on how to proceed, e.g. by downloading their ticket.

Free Order
    This e-mail is sent out instead of "Placed Order" and "Paid Order" if the order total is zero. It therefore should
    tell the same information, except asking the customer for completing their payment.

Resend link
    Sent by admin
        This e-mail will be sent out if you click the "Resend link" next to the e-mail address field on the order detail
        page. It should include the link to the order and can be sent to users e.g. if they lost their original e-mails.

    Requested by user
        Customers can also request a link to all orders they created using their e-mail address themselves by filling
        out a form on the website. In this case, they will receive an e-mail containing a list of all orders they created
        with the respective links.

Order changed
    This e-mail is sent out if you change the content of the order and choose to notify the user about it.

Payment reminder
    This e-mail is sent out a certain number of days before the order's expiry date. You can specify the number of days
    before the expiry date that this should happen and the e-mail will only ever be sent if you do specify such a
    number. The text should ask the customer to complete the payment, tell the options on how to do so and the
    consequences if no payment is received (ticket gone, depending on your other settings). You should also include
    a way to contact you in case of questions.

Waiting list notification
    If you enable the waiting list feature, this is the mail that will be sent out if a ticket is assigned to a person on
    the waiting list. It should include the voucher that needs to be redeemed to get the free spot and tell how long
    that voucher is valid and where to redeem it.

Order canceled
    This e-mail is sent to a customer if their order has been canceled.


Order custom mail
    You can use pretix' admin interface to directly send an e-mail with a custom text to the customer of a specific
    order. In this case, this will be the default text and might save you time by not having to re-type all of it every
    time.

Reminder to download tickets
    If you want, you can configure an email that will be send out a number of days before your event to remind
    attendees to download their tickets. The e-mail should include a link to the ticket download. This e-mail will only
    ever be sent if you specify a number of days.

Order approval process
    If you configure one of your products to "require approval", orders of that product will not immediately be confirmed
    but only after you approved them manually. In this case, the following e-mail templates will be sent out.

    Received order
        After an order has been received, this e-mail will be sent automatically instead of the "order placed" e-mail from
        above.

    Approved order
        This e-mail will be sent after you manually approved an order. This should include instructions to pay for the order,
        which is why this will only be used for a paid order. For a free order, the "free order" e-mail from above will
        be sent.

    Denied order
        This e-mail will be sent out to customers when their order has been denied.

SMTP settings
-------------

If you want to send your e-mails via your own e-mail address, we strongly recommend to use SMTP for this purpose.
SMTP is a protocol that is used by e-mail clients to communicate with e-mail servers. Using SMTP, pretix can talk to
your e-mail service provider the same way that e.g. the e-mail app on your phone can.

Your e-mail provider will most likely have a document that tells you the settings for the various fields to fill in
here (hostname, port, username, password, encryption).

With the checkbox "Use custom SMTP server" you can turn using your SMTP server on or off completely. With the
button "Save and test custom SMTP connection", you can test if the connection and authentication to your SMTP server
succeeds, even before turning that checkbox on.

Spam issues
-----------

If you use an email address of your own domain as a sender address and do not use a custom SMTP server, it is very
likely that at least some of your emails will go to the spam folders of their recipients. We **strongly recommend**
to use your organization's SMTP server in this case, making your email really come from your organization. If you don't
want that or cannot do that, you should add the pretix application server to your SPF record.

If you are using our hosted service at pretix.eu, you can add the following to your SPF record::

   include:_spf.pretix.eu

A complete record could look like this::

   v=spf1 a mx include:_spf.pretix.eu ~all

Make sure to read up on the `SPF specification`_. If you want to authenticate your emails with DKIM, set up a DNS TXT
record for the subdomain ``pretix._domainkey`` with the following contents::

   v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDXrDk6lwOWX00e2MbiiJac6huI+gnzLf9N4G1FnBv3PXq8fz3i2q1szH72OF5mAlKm3zXO4cl/uxx+lfidS1ERbX6Bn9BRstBTQUKWC4JFj8Yk9+fwT7LWehDURazLdTzfsIjJFudLLvxtOKSaOCtMhbPX05DIhziaqVCBqgz/NQIDAQAB

Then, please contact support@pretix.eu and we will enable DKIM for your domain on our mail servers.


.. _Sender Policy Framework: https://en.wikipedia.org/wiki/Sender_Policy_Framework
.. _SPF specification: http://www.openspf.org/SPF_Record_Syntax
