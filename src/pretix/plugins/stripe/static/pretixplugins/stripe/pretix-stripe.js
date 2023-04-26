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

        // ToDo: 'card' --> proper type of payment method
        pretixstripe.stripe.createPaymentMethod('card', pretixstripe.card).then(function (result) {
            waitingDialog.hide();
            if (result.error) {
                $(".stripe-errors").stop().hide().removeClass("sr-only");
                $(".stripe-errors").html("<div class='alert alert-danger'>" + result.error.message + "</div>");
                $(".stripe-errors").slideDown();
            } else {
                var $form = $("#stripe_payment_method_id").closest("form");
                // Insert the token into the form so it gets submitted to the server
                $("#stripe_payment_method_id").val(result.paymentMethod.id);
                $("#stripe_card_brand").val(result.paymentMethod.card.brand);
                $("#stripe_card_last4").val(result.paymentMethod.card.last4);
                // and submit
                $form.get(0).submit();
            }
        }).catch((e) => {
            waitingDialog.hide();
            $(".stripe-errors").stop().hide().removeClass("sr-only");
            $(".stripe-errors").html("<div class='alert alert-danger'>Technical error, please contact support: " + e + "</div>");
            $(".stripe-errors").slideDown();
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
                            stripeAccount: $.trim($("#stripe_connectedAccountId").html()),
                            locale: $.trim($("body").attr("data-locale"))
                        });
                    } else {
                        pretixstripe.stripe = Stripe($.trim($("#stripe_pubkey").html()), {
                            locale: $.trim($("body").attr("data-locale"))
                        });
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

                            pretixstripe.paymentRequest.on('paymentmethod', function (ev) {
                                ev.complete('success');

                                var $form = $("#stripe_payment_method_id").closest("form");
                                // Insert the token into the form so it gets submitted to the server
                                $("#stripe_payment_method_id").val(ev.paymentMethod.id);
                                $("#stripe_card_brand").val(ev.paymentMethod.card.brand);
                                $("#stripe_card_last4").val(ev.paymentMethod.card.last4);
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
                    pretixstripe.card.on('ready', function () {
                       $('.stripe-container').closest("form").find(".checkout-button-row .btn-primary").prop("disabled", false);
                    });
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
                }
            }
        );
    },
    'handleCardAction': function (payment_intent_client_secret) {
        $.ajax({
            url: 'https://js.stripe.com/v3/',
            dataType: 'script',
            success: function () {
                if ($.trim($("#stripe_connectedAccountId").html())) {
                    pretixstripe.stripe = Stripe($.trim($("#stripe_pubkey").html()), {
                        stripeAccount: $.trim($("#stripe_connectedAccountId").html()),
                        locale: $.trim($("body").attr("data-locale"))
                    });
                } else {
                    pretixstripe.stripe = Stripe($.trim($("#stripe_pubkey").html()), {
                        locale: $.trim($("body").attr("data-locale"))
                    });
                }
                pretixstripe.stripe.handleCardAction(
                    payment_intent_client_secret
                ).then(function (result) {
                    waitingDialog.show(gettext("Confirming your payment …"));
                    location.reload();
                });
            }
        });
    },
    'handleCardActioniFrame': function (payment_intent_next_action_redirect_url) {
        waitingDialog.show(gettext("Contacting your bank …"));
        let iframe = document.createElement('iframe');
        iframe.src = payment_intent_next_action_redirect_url;
        iframe.className = 'embed-responsive-item';
        $('#scacontainer').append(iframe);
        $('#scacontainer iframe').on("load", function () {
            waitingDialog.hide();
        });
    }
};
$(function () {
    if ($("#stripe_payment_intent_SCA_status").length) {
        window.parent.postMessage('3DS-authentication-complete.' + $.trim($("#order_status").html()), '*');
        return;
    } else if ($("#stripe_payment_intent_next_action_redirect_url").length) {
        let payment_intent_next_action_redirect_url = $.trim($("#stripe_payment_intent_next_action_redirect_url").html());
        pretixstripe.handleCardActioniFrame(payment_intent_next_action_redirect_url);
    } else if ($("#stripe_payment_intent_client_secret").length) {
        let payment_intent_client_secret = $.trim($("#stripe_payment_intent_client_secret").html());
        pretixstripe.handleCardAction(payment_intent_client_secret);
    }

    $(window).on("message onmessage", function(e) {
        if (typeof e.originalEvent.data === "string" && e.originalEvent.data.startsWith('3DS-authentication-complete.')) {
            waitingDialog.show(gettext("Confirming your payment …"));
            $('#scacontainer').hide();
            $('#continuebutton').removeClass('hidden');

            if (e.originalEvent.data.split('.')[1] == 'p') {
                window.location.href = $('#continuebutton').attr('href') + '?paid=yes';
            } else {
                window.location.href = $('#continuebutton').attr('href');
            }
        }
    });

    if (!$(".stripe-container").length)
        return;

    if ($("input[name=payment][value=stripe]").is(':checked') || $(".payment-redo-form").length) {
          pretixstripe.load();
    } else {
        $("input[name=payment]").change(function () {
            if ($(this).val() === 'stripe') {
                pretixstripe.load();
            }
        })
    }

    $("#stripe_other_card").click(
        function (e) {
            $("#stripe_payment_method_id").val("");
            $("#stripe-current-card").slideUp();
            $("#stripe-elements").slideDown();

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
                && $("#stripe_payment_method_id").val() == "") {
                pretixstripe.cc_request();
                return false;
            }
        }
    );
});