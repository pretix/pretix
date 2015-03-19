'use strict';

var pretixstripe = {
    'validate_number': function () {
        var numb = $("#stripe_number").val();
        $(".stripe-number").addClass("has-feedback");
        if (Stripe.card.validateCardNumber(numb)) {
            $(".stripe-number").addClass("has-success").removeClass("has-error");
            $(".stripe-number .form-control-feedback").addClass("fa-check")
                .removeClass("fa-remove").removeClass("sr-only");
        } else {
            $(".stripe-number").removeClass("has-success").addClass("has-error");
            $(".stripe-number .form-control-feedback").addClass("fa-remove")
                .removeClass("fa-ok").removeClass("sr-only");
        }
    },
    'validate_expire': function () {
        var month = $("#stripe_exp_month").val();
        var year = $("#stripe_exp_year").val();
        $(".stripe-exp").addClass("has-feedback");
        if (Stripe.card.validateExpiry(month, year)) {
            $(".stripe-exp").addClass("has-success").removeClass("has-error");
            $(".stripe-exp .form-control-feedback").addClass("fa-check")
                .removeClass("fa-remove").removeClass("sr-only");
        } else {
            $(".stripe-exp").removeClass("has-success").addClass("has-error");
            $(".stripe-exp .form-control-feedback").addClass("fa-remove")
                .removeClass("fa-ok").removeClass("sr-only");
        }
    },
    'validate_cvc': function () {
        var cvc = $("#stripe_cvc").val();
        $(".stripe-cvc").addClass("has-feedback");
        if (Stripe.card.validateCVC(cvc)) {
            $(".stripe-cvc").addClass("has-success").removeClass("has-error");
            $(".stripe-cvc .form-control-feedback").addClass("fa-check")
                .removeClass("fa-remove").removeClass("sr-only");
        } else {
            $(".stripe-cvc").removeClass("has-success").addClass("has-error");
            $(".stripe-cvc .form-control-feedback").addClass("fa-remove")
                .removeClass("fa-ok").removeClass("sr-only");
        }
    },
    'request': function () {
        waitingDialog.show(stripe_loading_message);
        $(".stripe-errors").hide();
        Stripe.card.createToken(
            {
                number: $('#stripe_number').val(),
                cvc: $('#stripe_cvc').val(),
                exp_month: $('#stripe_exp_month').val(),
                exp_year: $('#stripe_exp_year').val(),
                name: $('#stripe_name').val(),
            },
            pretixstripe.response
        );
    },
    'response': function (status, response) {
        var $form = $("#stripe_number").parents("form");
        waitingDialog.hide();
        if (response.error) {
            $(".stripe-errors").stop().hide().removeClass("sr-only");
            $(".stripe-errors").html("<div class='alert alert-danger'>" + response.error.message + "</div>");
            $(".stripe-errors").slideDown();
        } else {
            var token = response.id;
            // Insert the token into the form so it gets submitted to the server
            $("#stripe_token").val(token);
            $("#stripe_card_brand").val(response.card.brand);
            $("#stripe_card_last4").val(response.card.last4);
            // and submit
            $form.get(0).submit();
        }
    }
};
$(function() {
    if (!$("#stripe_number").length) // Not on the checkout page
        return;

    $("#stripe_number").change(pretixstripe.validate_number).keydown(pretixstripe.validate_number)
        .keyup(pretixstripe.validate_number);
    $(".stripe-exp input").change(pretixstripe.validate_expire).keydown(pretixstripe.validate_expire)
        .keyup(pretixstripe.validate_expire)
    $("#stripe_cvc").change(pretixstripe.validate_cvc).keydown(pretixstripe.validate_cvc)
        .keyup(pretixstripe.validate_cvc)
    $("#stripe_number").parents("form").submit(
        function () {
            if ($("input[name=payment][value=stripe]").prop('checked') && $("#stripe_token").val() == "") {
                pretixstripe.request();
                return false;
            }
        }
    );
});