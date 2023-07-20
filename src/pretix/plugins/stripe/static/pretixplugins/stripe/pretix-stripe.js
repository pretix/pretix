/*global $, stripe_pubkey, stripe_loadingmessage, gettext */
'use strict';

var pretixstripe = {
    stripe: null,
    elements: null,
    card: null,
    sepa: null,
    paymentRequest: null,
    paymentRequestButton: null,

    'pm_request': function (method, element, kwargs = {}) {
        waitingDialog.show(gettext("Contacting Stripe …"));
        $(".stripe-errors").hide();

        pretixstripe.stripe.createPaymentMethod(method, element, kwargs).then(function (result) {
            waitingDialog.hide();
            if (result.error) {
                $(".stripe-errors").stop().hide().removeClass("sr-only");
                $(".stripe-errors").html("<div class='alert alert-danger'>" + result.error.message + "</div>");
                $(".stripe-errors").slideDown();
            } else {
                var $form = $("#stripe_" + method + "_payment_method_id").closest("form");
                // Insert the token into the form so it gets submitted to the server
                $("#stripe_" + method + "_payment_method_id").val(result.paymentMethod.id);
                if (method === 'card') {
                    $("#stripe_card_brand").val(result.paymentMethod.card.brand);
                    $("#stripe_card_last4").val(result.paymentMethod.card.last4);
                }
                if (method === 'sepa_debit') {
                    $("#stripe_sepa_debit_last4").val(result.paymentMethod.sepa_debit.last4);
                }
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
                                currency: $("#stripe_card_currency").val().toLowerCase(),
                                total: {
                                    label: gettext('Total'),
                                    amount: parseInt($("#stripe_card_total").val())
                                },
                                displayItems: [],
                                requestPayerName: false,
                                requestPayerEmail: false,
                                requestPayerPhone: false,
                                requestShipping: false,
                            });

                            pretixstripe.paymentRequest.on('paymentmethod', function (ev) {
                                ev.complete('success');

                                var $form = $("#stripe_card_payment_method_id").closest("form");
                                // Insert the token into the form so it gets submitted to the server
                                $("#stripe_card_payment_method_id").val(ev.paymentMethod.id);
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
                        pretixstripe.card.on('ready', function () {
                            $('.stripe-container').closest("form").find(".checkout-button-row .btn-primary").prop("disabled", false);
                        });
                    }
                    if ($("#stripe-sepa").length) {
                        pretixstripe.sepa = pretixstripe.elements.create('iban', {
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
                            supportedCountries: ['SEPA'],
                            classes: {
                                focus: 'is-focused',
                                invalid: 'has-error',
                            }
                        });
                        pretixstripe.sepa.on('change', function (event) {
                            // List of IBAN-countries, that require the country as well as line1-property according to
                            // https://stripe.com/docs/payments/sepa-debit/accept-a-payment?platform=web&ui=element#web-submit-payment
                            if (['AD', 'PF', 'TF', 'GI', 'GB', 'GG', 'VA', 'IM', 'JE', 'MC', 'NC', 'BL', 'PM', 'SM', 'CH', 'WF'].indexOf(event.country) > 0) {
                                $("#stripe_sepa_debit_country").prop('checked', true);
                                $("#stripe_sepa_debit_country").change();
                            } else {
                                $("#stripe_sepa_debit_country").prop('checked', false);
                                $("#stripe_sepa_debit_country").change();
                            }
                            if (event.bankName) {
                                $("#stripe_sepa_debit_bank").val(event.bankName);
                            }
                        });
                        pretixstripe.sepa.mount("#stripe-sepa");
                        pretixstripe.sepa.on('ready', function () {
                            $('.stripe-container').closest("form").find(".checkout-button-row .btn-primary").prop("disabled", false);
                        });
                    }
                    if ($("#stripe-payment-request-button").length && pretixstripe.paymentRequest != null) {
                        pretixstripe.paymentRequestButton = pretixstripe.elements.create('paymentRequestButton', {
                            paymentRequest: pretixstripe.paymentRequest,
                        });

                        pretixstripe.paymentRequest.canMakePayment().then(function (result) {
                            if (result) {
                                pretixstripe.paymentRequestButton.mount('#stripe-payment-request-button');
                                $('#stripe-card-elements .stripe-or').removeClass("hidden");
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

    $(window).on("message onmessage", function (e) {
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

    if ($("input[name=payment][value=stripe]").is(':checked') || $("input[name=payment][value=stripe_sepa_debit]").is(':checked') || $(".payment-redo-form").length) {
        pretixstripe.load();
    } else {
        $("input[name=payment]").change(function () {
            if (['stripe', 'stripe_sepa_debit'].indexOf($(this).val()) > -1) {
                pretixstripe.load();
            }
        })
    }

    $("#stripe_other_card").click(
        function (e) {
            $("#stripe_card_payment_method_id").val("");
            $("#stripe-current-card").slideUp();
            $("#stripe-card-elements").slideDown();

            e.preventDefault();
            return false;
        }
    );

    if ($("#stripe-current-card").length) {
        $("#stripe-card-elements").hide();
    }

    $("#stripe_other_account").click(
        function (e) {
            $("#stripe_sepa_debit_payment_method_id").val("");
            $("#stripe-current-account").slideUp();
            // We're using a css-selector here instead of the id-selector,
            // as we're hiding Stripe Elements *and* Django form fields
            $('.stripe-sepa_debit-form').slideDown();

            e.preventDefault();
            return false;
        }
    );

    if ($("#stripe-current-account").length) {
        // We're using a css-selector here instead of the id-selector,
        // as we're hiding Stripe Elements *and* Django form fields
        $('.stripe-sepa_debit-form').hide();
    }

    $('.stripe-container').closest("form").submit(
        function () {
            if ($("input[name=card_new]").length && !$("input[name=card_new]").prop('checked')) {
                return null;
            }
            if (($("input[name=payment][value=stripe]").prop('checked') || $("input[name=payment][type=radio]").length === 0)
                && $("#stripe_card_payment_method_id").val() == "") {
                pretixstripe.pm_request('card', pretixstripe.card);
                return false;
            }

            if (($("input[name=payment][value=stripe_sepa_debit]").prop('checked')) && $("#stripe_sepa_debit_payment_method_id").val() == "") {
                pretixstripe.pm_request('sepa_debit', pretixstripe.sepa, {
                    billing_details: {
                        name: $("#id_payment_stripe_sepa_debit-accountname").val(),
                        email: $("#stripe_sepa_debit_email").val(),
                        address: {
                            line1: $("#id_payment_stripe_sepa_debit-line1").val(),
                            postal_code: $("#id_payment_stripe_sepa_debit-postal_code").val(),
                            city: $("#id_payment_stripe_sepa_debit-city").val(),
                            country: $("#id_payment_stripe_sepa_debit-country").val(),
                        }
                    }
                });
                return false;
            }
        }
    );
});