/*global $, stripe_pubkey, stripe_loadingmessage, gettext */
'use strict';

var Stripe = null;
var pretixstripe = {
    'load': function () {
        $.ajax(
            {
                url: 'https://checkout.stripe.com/checkout.js',
                dataType: 'script',
                success: function () {
                    pretixstripe.handler = StripeCheckout.configure({
                        key: $.trim($("#stripe_pubkey").html()),
                        locale: 'auto',
                        token: function(token) {
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
                }
            }
        );
    },

    start: function () {
        var amount = Math.round(
            parseFloat(
                $("#stripe-checkout").parents("[data-total]").attr("data-total").replace(",", ".")
            ) * 100
        );
        pretixstripe.handler.open({
            name: $("#organizer_name").val(),
            description: $("#event_name").val(),
            currency: $("#stripe_currency").val(),
            email: $("#stripe_email").val(),
            amount: amount
        });
    },

    handler: null
};
$(function () {
    if (!$("#stripe-checkout").length) {  // Not on the checkout page
        return;
    }

    if ($("input[name=payment][value=stripe]").is(':checked') || $(".payment-redo-form").length) {
        pretixstripe.load();
    } else {
        $("input[name=payment]").change(function() {
            if ($(this).val() == 'stripe') {
                pretixstripe.load();
            }
        })
    }

    $(".checkout-button-row .btn-primary").click(
        function (e) {
            if (($("input[name=payment][value=stripe]").prop('checked') || $("input[type=checkbox][name=radio]").length === 0)
                && $("#stripe_token").val() == "") {
                pretixstripe.start();
                e.preventDefault();
                return false;
            }
        }
    );

    $("#stripe_other_card").click(
        function (e) {
            pretixstripe.start();
            e.preventDefault();
            return false;
        }
    );

    $(window).on('popstate', function () {
        if (pretixstripe.handler) {
            pretixstripe.handler.close();
        }
    });
});
