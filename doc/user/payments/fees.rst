.. _payment-fees:

Payment method fees
===================

Most external payment providers like PayPal or Stripe charge substantial fees for your service. In general, you have
two options to deal with this:

1. Pay the fees yourself

2. Add the fees to your customer's total

The choice totally depends on you and what your customers expect from you. Option two might be appropriate if you
offer different payment methods and want to encourage your customers to use the ones that come you cheaper, but you
might also decide to go for option one to make it easier for customers who don't have the option.

.. warning:: Please note that EU Directive 2015/2366 bans surcharging payment fees for most common payment
             methods within the European Union. Depending on the payment method, this might affect
             selling to consumers only or to business customers as well. Depending on your country, this
             legislation might already be in place or become relevant from January 2018 the latest. This is not
             legal advice. If in doubt, consult a lawyer or refrain from charging payment fees.

If you go for the first option (as you should in the EU), you can just leave the payment fee fields in pretix' settings
empty.

If you go for the second option, you can configure pretix to charge the payment method fees to your user. You can
define both an absolute fee as well as a percental fee based on the order total. If you do so, there are two
different ways in which pretix can calculate the fee. Normally, it is fine to just go with the default setting, but
in case you are interested, here are all the details:

Payment fee calculation
-----------------------

If you configure a fee for a payment method, there are two possible ways for us to calculate this. Let's
assume that your payment provider, e.g. PayPal, charges you 5 % fees and you want to charge your users the
same 5 %, such that for a ticket with a list price of 100 € you will get your full 100 €.

**Method A: Calculate the fee from the subtotal and add it to the bill.**

    For a ticket price of 100 €, this will lead to the following calculation:

    ============================================== ============
    Ticket price                                       100.00 €
    pretix calculates the fee as 5 % of 100 €           +5.00 €
    Subtotal that will be paid by the customer         105.00 €
    PayPal calculates its fee as 5 % of 105 €           -5.25 €
    End total that is on your bank account          **99.75 €**
    ============================================== ============

**Method B (default): Calculate the fee from the total value including the fee.**

    For a ticket price of 100 €, this will lead to the following calculation:

    ===================================================== =============
    Ticket price                                               100.00 €
    pretix calculates the fee as 100/(100 - 5) % of 100 €       +5.26 €
    Subtotal that will be paid by the customer                 105.26 €
    PayPal calculates its fee as 5 % of 105 €                   -5.26 €
    End total that is on your bank account                 **100.00 €**
    ===================================================== =============

    Due to the various rounding steps performed by pretix and by the payment provider, the end total on
    your bank account might still vary by one cent.
