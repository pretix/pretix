/*global $, stripe_pubkey, stripe_loadingmessage, gettext */
'use strict';

var pretixstripe = {
    stripe: null,
    elements: null,
    card: null,

    'request': function () {
        waitingDialog.show(gettext("Contacting Stripe …"));
        $(".stripe-errors").hide();

        pretixstripe.stripe.createToken(pretixstripe.card).then(function (result) {
            waitingDialog.hide();
            if (result.error) {
                $(".stripe-errors").stop().hide().removeClass("sr-only");
                $(".stripe-errors").html("<div class='alert alert-danger'>" + result.error.message + "</div>");
                $(".stripe-errors").slideDown();
            } else {
                var $form = $("#stripe_token").closest("form");
                // Insert the token into the form so it gets submitted to the server
                $("#stripe_token").val(result.token.id);
                $("#stripe_card_brand").val(result.token.card.brand);
                $("#stripe_card_last4").val(result.token.card.last4);
                // and submit
                $form.get(0).submit();
            }
        });
    },
    'load': function () {
        $.ajax(
            {
                url: 'https://js.stripe.com/v3/',
                dataType: 'script',
                success: function () {
                    pretixstripe.stripe = Stripe($.trim($("#stripe_pubkey").html()));
                    pretixstripe.elements = pretixstripe.stripe.elements();
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
            }
        );
    }
};
$(function () {
    if (!$("#stripe-card").length) // Not on the checkout page
        return;

    if ($("input[name=payment][value=stripe]").is(':checked') || $(".payment-redo-form").length) {
        pretixstripe.load();
    } else {
        $("input[name=payment]").change(function () {
            if ($(this).val() == 'stripe') {
                pretixstripe.load();
            }
        })
    }

    $("#stripe_other_card").click(
        function (e) {
            $("#stripe_token").val("");
            $("#stripe-current-card").slideUp();
            $("#stripe-card").slideDown();
            pretixstripe.start();
            e.preventDefault();
            return false;
        }
    );

    if ($("#stripe-current-card").length) {
        $("#stripe-card").hide();
    }

    $("#stripe-card").parents("form").submit(
        function () {
            if (($("input[name=payment][value=stripe]").prop('checked') || $("input[name=payment]").length === 0)
                && $("#stripe_token").val() == "") {
                pretixstripe.request();
                return false;
            }
        }
    );
});
