.. highlight:: python
   :linenothreshold: 5

Writing a payment provider plugin
=================================

In this document, we will walk through the creation of a payment provider plugin. This
is very similar to creating an export output.

Please read :ref:`Creating a plugin <pluginsetup>` first, if you haven't already.

.. warning:: We changed our payment provider API a lot in pretix 2.x. Our documentation page on :ref:`payment2.0`
             might be insightful even if you do not have a payment provider to port, as it outlines the rationale
             behind the current design.

Provider registration
---------------------

The payment provider API does not make a lot of usage from signals, however, it
does use a signal to get a list of all available payment providers. Your plugin
should listen for this signal and return the subclass of ``pretix.base.payment.BasePaymentProvider``
that the plugin will provide:

.. code-block:: python

    from django.dispatch import receiver

    from pretix.base.signals import register_payment_providers


    @receiver(register_payment_providers, dispatch_uid="payment_paypal")
    def register_payment_provider(sender, **kwargs):
        from .payment import Paypal
        return Paypal


The provider class
------------------

.. py:class:: pretix.base.payment.BasePaymentProvider

   The central object of each payment provider is the subclass of ``BasePaymentProvider``.

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

   .. autoattribute:: public_name

   .. autoattribute:: is_enabled

   .. autoattribute:: priority

   .. autoattribute:: settings_form_fields

   .. automethod:: settings_form_clean

   .. automethod:: settings_content_render

   .. automethod:: is_allowed

   .. automethod:: payment_form_render

   .. automethod:: payment_form

   .. autoattribute:: payment_form_fields

   .. automethod:: payment_is_valid_session

   .. automethod:: checkout_prepare

   .. automethod:: checkout_confirm_render

      This is an abstract method, you **must** override this!

   .. automethod:: execute_payment

   .. automethod:: calculate_fee

   .. automethod:: order_pending_mail_render

   .. automethod:: payment_pending_render

   .. autoattribute:: abort_pending_allowed

   .. automethod:: render_invoice_text

   .. automethod:: order_change_allowed

   .. automethod:: payment_prepare

   .. automethod:: payment_control_render

   .. automethod:: payment_control_render_short

   .. automethod:: payment_refund_supported

   .. automethod:: payment_partial_refund_supported

   .. automethod:: payment_presale_render

   .. automethod:: execute_refund

   .. automethod:: refund_control_render

   .. automethod:: new_refund_control_form_render

   .. automethod:: new_refund_control_form_process

   .. automethod:: api_payment_details

   .. automethod:: matching_id

   .. automethod:: shred_payment_info

   .. automethod:: cancel_payment

   .. autoattribute:: is_implicit

   .. autoattribute:: is_meta

   .. autoattribute:: test_mode_message

   .. autoattribute:: requires_invoice_immediately


Additional views
----------------

See also: :ref:`customview`.

For most simple payment providers it is more than sufficient to implement
some of the :py:class:`BasePaymentProvider` methods. However, in some cases
it is necessary to introduce additional views. One example is the PayPal
provider. It redirects the user to a PayPal website in the
:py:meth:`BasePaymentProvider.checkout_prepare` step of the checkout process
and provides PayPal with a URL to redirect back to. This URL points to a
view which looks roughly like this:

.. code-block:: python

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
                # information into a URL parameter.
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
inside :py:meth:`BasePaymentProvider.checkout_is_valid_session`. However,
because some external providers (not PayPal) force you to have a *constant*
redirect URL, it might be necessary to define custom views.
