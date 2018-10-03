/*global $, stripe_pubkey, stripe_loadingmessage, gettext */
'use strict';

var pretixstripe = {
    stripe: null,
    elements: null,
    card: null,
    paymentRequest: null,
    paymentRequestButton: null,

    'cc_request': function () {
        waitingDialog.show(gettext("Contacting Stripe …"));
        $(".stripe-errors").hide();

        pretixstripe.stripe.createSource(pretixstripe.card).then(function (result) {
            waitingDialog.hide();
            if (result.error) {
                $(".stripe-errors").stop().hide().removeClass("sr-only");
                $(".stripe-errors").html("<div class='alert alert-danger'>" + result.error.message + "</div>");
                $(".stripe-errors").slideDown();
            } else {
                var $form = $("#stripe_token").closest("form");
                // Insert the token into the form so it gets submitted to the server
                $("#stripe_token").val(result.source.id);
                $("#stripe_card_brand").val(result.source.card.brand);
                $("#stripe_card_last4").val(result.source.card.last4);
                // and submit
                $form.get(0).submit();
            }
        });
    },
    'load': function () {
      if (pretixstripe.stripe !== null) {
          return;
      }
      $('.stripe-container').closest("form").find(".checkout-button-row .btn-primary").prop("disabled", true);
        $.ajax(
            {
                url: 'https://js.stripe.com/v3/',
                dataType: 'script',
                success: function () {
                    if ($.trim($("#stripe_connectedAccountId").html())) {
                        pretixstripe.stripe = Stripe($.trim($("#stripe_pubkey").html()), {
                            stripeAccount: $.trim($("#stripe_connectedAccountId").html())
                        });
                    } else {
                        pretixstripe.stripe = Stripe($.trim($("#stripe_pubkey").html()));
                    }
                    pretixstripe.elements = pretixstripe.stripe.elements();
                    if ($.trim($("#stripe_merchantcountry").html()) !== "") {
                        try {
                            pretixstripe.paymentRequest = pretixstripe.stripe.paymentRequest({
                                country: $("#stripe_merchantcountry").html(),
                                currency: $("#stripe_currency").val().toLowerCase(),
                                total: {
                                    label: gettext('Total'),
                                    amount: parseInt($("#stripe_total").val())
                                },
                                displayItems: [],
                                requestPayerName: false,
                                requestPayerEmail: false,
                                requestPayerPhone: false,
                                requestShipping: false,
                            });

                            pretixstripe.paymentRequest.on('token', function (ev) {
                                ev.complete('success');

                                var $form = $("#stripe_token").closest("form");
                                // Insert the token into the form so it gets submitted to the server
                                $("#stripe_token").val(ev.token.id);
                                $("#stripe_card_brand").val(ev.token.card.brand);
                                $("#stripe_card_last4").val(ev.token.card.last4);
                                // and submit
                                $form.get(0).submit();
                            });
                        } catch (e) {
                            pretixstripe.paymentRequest = null;
                        }
                    } else {
                        pretixstripe.paymentRequest = null;
                    }
                    if ($("#stripe-card").length) {
                        pretixstripe.card = pretixstripe.elements.create('card', {
                            'style': {
                                'base': {
                                    'fontFamily': '"Open Sans","OpenSans","Helvetica Neue",Helvetica,Arial,sans-serif',
                                    'fontSize': '14px',
                                    'color': '#555555',
                                    'lineHeight': '1.42857',
                                    'border': '1px solid #ccc',
                                    '::placeholder': {
                                        color: 'rgba(0,0,0,0.4)',
                                    },
                                },
                                'invalid': {
                                    'color': 'red',
                                },
                            },
                            classes: {
                                focus: 'is-focused',
                                invalid: 'has-error',
                            }
                        });
                        pretixstripe.card.mount("#stripe-card");
                    }
                    if ($("#stripe-payment-request-button").length && pretixstripe.paymentRequest != null) {
                      pretixstripe.paymentRequestButton = pretixstripe.elements.create('paymentRequestButton', {
                        paymentRequest: pretixstripe.paymentRequest,
                      });

                      pretixstripe.paymentRequest.canMakePayment().then(function(result) {
                        if (result) {
                          pretixstripe.paymentRequestButton.mount('#stripe-payment-request-button');
                          $('#stripe-elements .stripe-or').removeClass("hidden");
                          $('#stripe-payment-request-button').parent().removeClass("hidden");
                        } else {
                          $('#stripe-payment-request-button').hide();
                          document.getElementById('stripe-payment-request-button').style.display = 'none';
                        }
                      });
                    }
                    $('.stripe-container').closest("form").find(".checkout-button-row .btn-primary").prop("disabled", false);
                }
            }
        );
    },
    'load_checkout': function () {
      if (pretixstripe.checkout_handler !== null) {
        return;
      }
      $('.stripe-container').closest("form").find(".checkout-button-row .btn-primary").prop("disabled", true);
        $.ajax(
            {
                url: 'https://checkout.stripe.com/checkout.js',
                dataType: 'script',
                success: function () {
                    pretixstripe.checkout_handler = StripeCheckout.configure({
                        key: $.trim($("#stripe_pubkey").html()),
                        locale: 'auto',
                        token: function (token) {
                            var $form = $("#stripe-checkout").parents("form");
                            $("#stripe_token").val(token.id);
                            $("#stripe_card_brand").val(token.card.brand);
                            $("#stripe_card_last4").val(token.card.last4);
                            $("#stripe_card_brand_display").text(token.card.brand);
                            $("#stripe_card_last4_display").text(token.card.last4);
                            $($form.get(0)).submit();
                        },
                        shippingAddress: false,
                        allowRememberMe: false,
                        billingAddress: false
                    });
                    $('.stripe-container').closest("form").find(".checkout-button-row .btn-primary").prop("disabled", false);
                }
            }
        );
    },
    'show_checkout': function () {
        var amount = Math.round(
            parseFloat(
                $("#stripe-checkout").parents("[data-total]").attr("data-total").replace(",", ".")
            ) * 100
        );
        pretixstripe.checkout_handler.open({
            name: $("#organizer_name").val(),
            description: $("#event_name").val(),
            currency: $("#stripe_currency").val(),
            email: $("#stripe_email").val(),
            amount: amount
        });
    },
    'checkout_handler': null
};
$(function () {
    if (!$(".stripe-container, #stripe-checkout").length) // Not on the checkout page
        return;

    if ($("input[name=payment][value=stripe]").is(':checked') || $(".payment-redo-form").length) {
        if ($("#stripe-checkout").length) {
            pretixstripe.load_checkout();
        } else {
          pretixstripe.load();
        }
    } else {
        $("input[name=payment]").change(function () {
            if ($(this).val() === 'stripe') {
                if ($("#stripe-checkout").length) {
                    pretixstripe.load_checkout();
                } else {
                    pretixstripe.load();
                }
            }
        })
    }

    $("#stripe_other_card").click(
        function (e) {
            $("#stripe_token").val("");
            if ($("#stripe-checkout").length) {
                pretixstripe.show_checkout();
            } else {
                $("#stripe-current-card").slideUp();
                $("#stripe-elements").slideDown();
            }
            e.preventDefault();
            return false;
        }
    );

    if ($("#stripe-current-card").length) {
        $("#stripe-elements").hide();
    }

    $('.stripe-container').closest("form").submit(
        function () {
            if ($("input[name=card_new]").length && !$("input[name=card_new]").prop('checked')) {
                return null;
            }
            if (($("input[name=payment][value=stripe]").prop('checked') || $("input[name=payment][type=radio]").length === 0)
                && $("#stripe_token").val() == "") {
                if ($("#stripe-checkout").length) {
                    pretixstripe.show_checkout();
                } else {
                    pretixstripe.cc_request();
                }
                return false;
            }
        }
    );
    $(window).on('popstate', function () {
        if (pretixstripe.checkout_handler) {
            pretixstripe.checkout_handler.close();
        }
    });
});
