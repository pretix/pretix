.. highlight:: python
   :linenothreshold: 5

Writing a payment provider plugin
=================================

In this document, we will walk through the creation of a payment provider plugin.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

Provider registration
---------------------

The payment provider API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available payment providers. Your plugin
should listen for this signal and return the subclass of ``pretix.base.payment.BasePaymentProvider``
that we'll soon create::

    from django.dispatch import receiver

    from pretix.base.signals import register_payment_providers

    from .payment import Paypal


    @receiver(register_payment_providers)
    def register_payment_provider(sender, **kwargs):
        return Paypal


The provider class
------------------

.. class:: pretix.base.payment.BasePaymentProvider

   The central object of each payment provider is the subclass of ``BasePaymentProvider``
   we already mentioned above. In this section, we will discuss it's interface in detail.

   .. py:attribute:: BasePaymentProvider.event

      The default constructor sets this property to the event we are currently
      working for.

   .. py:attribute:: BasePaymentProvider.settings

      The default constructor sets this property to a ``SettingsSandbox`` object. You can
      use this object to store settings using its ``get`` and ``set`` methods. All settings
      you store are transparently prefixed, so you get your very own settings namespace.

   .. autoattribute:: identifier

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: verbose_name

      This is an abstract attribute, you **must** override this!

   .. autoattribute:: is_enabled

   .. automethod:: calculate_fee

   .. autoattribute:: settings_form_fields

   .. automethod:: checkout_form_render

   .. automethod:: checkout_form

   .. autoattribute:: checkout_form_fields

   .. automethod:: checkout_prepare

   .. automethod:: checkout_is_valid_session

   .. automethod:: checkout_confirm_render

      This is an abstract method, you **must** override this!

   .. automethod:: checkout_perform

   .. automethod:: order_pending_render

      This is an abstract method, you **must** override this!

   .. automethod:: order_paid_render


Additional views
----------------

For most simple payment providers it is more than sufficient to implement
some of the :py:class:`BasePaymentProvider` methods. However, in some cases
it is necessary to introduce additional views. One example is the PayPal
provider. It redirects the user to a paypal website in the
:py:meth:`BasePaymentProvider.checkout_prepare`` step of the checkout process
and provides PayPal with an URL to redirect back to. This URL points to a
view which looks roughly like this::

    @login_required
    def success(request):
        pid = request.GET.get('paymentId')
        payer = request.GET.get('PayerID')
        # We stored some information in the session in checkout_prepare(),
        # let's compare the new information to double-check that this is about
        # the same payment
        if pid == request.session['payment_paypal_id']:
            # Save the new information to the user's session
            request.session['payment_paypal_payer'] = payer
            try:
                # Redirect back to the confirm page. We chose to save the
                # event ID in the user's session. We could also put this
                # information into an URL parameter.
                event = Event.objects.current.get(identity=request.session['payment_paypal_event'])
                return redirect(reverse('presale:event.checkout.confirm', kwargs={
                    'event': event.slug,
                    'organizer': event.organizer.slug,
                }))
            except Event.DoesNotExist:
                pass  # TODO: Display error message
        else:
            pass  # TODO: Display error message

If you do not want to provide a view of your own, you could even let PayPal
redirect directly back to the confirm page and handle the query parameters
inside :py:meth:`BasePaymentProvider.checkout_is_valid_session``. However,
because some external providers (not PayPal) force you to have a *constant*
redirect URL, it might be necessary to define custom views.
