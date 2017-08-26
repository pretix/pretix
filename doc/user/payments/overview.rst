Payment method overview
=======================

pretix allows you to accept payments using a variety of payment methods to fit the needs of very different events.
This page gives you a short overview over them and links to more detailled descriptions in some cases.

Payment methods are built as pretix plugins. For this reason, you might first need to enable a certain plugin at
"Settings" → "Plugins" in your event settings. Then, you can configure them in detail at "Settings" -> "Payment".

If you host pretix on your own server, you might need to install a plugin first for some of the payment methods listed
on this page as well as for additional ones.

:ref:`stripe`
    Stripe is a US-based company that offers you an easy way to accept credit card payments from all over the world.
    To accept payments with Stripe, you need to have a Stripe merchant account that is easy to create. Click on the link
    above to get more details about the Stripe integration into pretix.

:ref:`paypal`
    If you want to accept online payments via PayPal, you can do so using pretix. You will need a PayPal merchant
    account and it is a little bit complicated to obtain the required technical details, but we've got you covered.
    Click on the link above to learn more.

:ref:`banktransfer`
    Classical IBAN wire transfers are a common payment method in central Europe that has the large benefit that it
    often does not cause any additional fees. However, it requires you to invest some more effort as you need to
    check your bank account for incoming payments regularly. We provide some tools to make this easier for you.

SEPA debit
    In some Europen countries, a very popular online payment method is SEPA direct debit. If you want to offer this
    option in your pretix ticket shop, we provide a convenient plugin that allows users to enter their SEPA bank
    account details and issue a SEPA mandate. You will then need to regularly download a SEPA XML file from pretix
    and upload it to your bank's interface to actually perform the debits.


