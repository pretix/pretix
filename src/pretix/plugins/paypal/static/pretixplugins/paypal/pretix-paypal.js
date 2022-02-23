/*global $, paypal_client_id, paypal_loadingmessage, gettext */
'use strict';

var pretixpaypal = {
    paypal: null,
    client_id: null,
    order_id: null,
    payer_id: null,
    merchant_id: null,
    currency: null,
    method: null,
    additional_disabled_funding: null,
    additional_enabled_funding: null,
    debug_buyer_country: null,
    continue_button: null,
    paypage: false,
    method_map: {
        wallet: {
            method: 'wallet',
            funding_source: 'paypal',
            //disable_funding: null,
            //enable_funding: 'paylater',
            early_auth: true,
        },
        apm: {
            method: 'apm',
            funding_source: null,
            //disable_funding: null,
            //enable_funding: null,
            early_auth: false,
        }
    },
    apm_map: {
        paypal: gettext('PayPal'),
        venmo: gettext('Venmo'),
        applepay: gettext('Apple Pay'),
        itau: gettext('Itaú'),
        credit: gettext('PayPal Credit'),
        card: gettext('Credit Card'),
        paylater: gettext('PayPal Pay Later'),
        ideal: gettext('iDEAL'),
        sepa: gettext('SEPA Direct Debit'),
        bancontact: gettext('Bancontact'),
        giropay: gettext('giropay'),
        sofort: gettext('SOFORT'),
        eps: gettext('eps'),
        mybank: gettext('MyBank'),
        p24: gettext('Przelewy24'),
        verkkopankki: gettext('Verkkopankki'),
        payu: gettext('PayU'),
        blik: gettext('BLIK'),
        trustly: gettext('Trustly'),
        zimpler: gettext('Zimpler'),
        maxima: gettext('Maxima'),
        oxxo: gettext('OXXO'),
        boleto: gettext('Boleto'),
        wechatpay: gettext('WeChat Pay'),
        mercadopago: gettext('Mercado Pago')
    },

    load: function () {
        if (pretixpaypal.paypal === null) {
            pretixpaypal.client_id = $.trim($("#paypal_client_id").html());
            pretixpaypal.merchant_id = $.trim($("#paypal_merchant_id").html());
            pretixpaypal.debug_buyer_country = $.trim($("#paypal_buyer_country").html());
            pretixpaypal.continue_button = $('.checkout-button-row').closest("form").find(".checkout-button-row .btn-primary");
            pretixpaypal.continue_button.closest('div').append('<div id="paypal-button-container"></div>');
            pretixpaypal.additional_disabled_funding = $.trim($("#paypal_disable_funding").html());
            pretixpaypal.additional_enabled_funding = $.trim($("#paypal_enable_funding").html());
            pretixpaypal.paypage = Boolean($('#paypal-button-container').data('paypage'));
            pretixpaypal.order_id = $.trim($("#paypal_oid").html());
            pretixpaypal.currency = $("body").attr("data-currency");
        }

        pretixpaypal.continue_button.prop("disabled", true);

        let sdk_url = 'https://www.paypal.com/sdk/js' +
            '?client-id=' + pretixpaypal.client_id +
            '&components=buttons,funding-eligibility' +
            '&currency=' + pretixpaypal.currency;

        if (pretixpaypal.merchant_id) {
            sdk_url += '&merchant-id=' + pretixpaypal.merchant_id;
        }

        if (pretixpaypal.additional_disabled_funding) {
            sdk_url += '&disable-funding=' + [pretixpaypal.additional_disabled_funding].filter(Boolean).join(',');
        }

        if (pretixpaypal.additional_enabled_funding) {
            sdk_url += '&enable-funding=' + [pretixpaypal.additional_enabled_funding].filter(Boolean).join(',');
        }

        if (pretixpaypal.debug_buyer_country) {
            sdk_url += '&buyer-country=' + pretixpaypal.debug_buyer_country;
        }

        let ppscript = document.createElement('script');
        let ready = false;
        let head = document.getElementsByTagName("head")[0];
        ppscript.setAttribute('src', sdk_url);
        ppscript.setAttribute('data-csp-nonce', $.trim($("#csp_nonce").html()));
        ppscript.setAttribute('data-page-type', 'checkout');
        ppscript.setAttribute('data-partner-attribution-id', 'ramiioGmbH_Cart_PPCP');
        document.head.appendChild(ppscript);

        ppscript.onload = ppscript.onreadystatechange = function () {
            if (!ready && (!this.readyState || this.readyState === "loaded" || this.readyState === "complete")) {
                ready = true;

                pretixpaypal.paypal = paypal;

                // Handle memory leak in IE
                ppscript.onload = ppscript.onreadystatechange = null;
                if (head && ppscript.parentNode) {
                    head.removeChild(ppscript);
                }
            }
        };
    },

    ready: function () {
        if ($("input[name=payment][value=paypal_apm]").length > 0) {
            pretixpaypal.renderAPMs();
        }

        $("input[name=payment][value^='paypal']").change(function () {
            pretixpaypal.renderButton($(this).val());
        });

        $("input[name=payment]").not("[value^='paypal']").change(function () {
            pretixpaypal.restore();
        });

        if ($("input[name=payment][value^='paypal']").is(':checked') || $(".payment-redo-form").length) {
            pretixpaypal.renderButton($("input[name=payment][value^='paypal']:checked").val());
        }

        if ($('#paypal-button-container').data('paypage')) {
            pretixpaypal.renderButton('paypal_apm');
        }
    },

    restore: function () {
        // if PayPal has not been initialized, there shouldn't be anything to cleanup
        if (pretixpaypal.paypal !== null) {
            $('#paypal-button-container').empty()
            pretixpaypal.continue_button.text(gettext('Continue'));
            pretixpaypal.continue_button.show();
            pretixpaypal.continue_button.prop("disabled", false);
        }
    },

    renderButton: function (method) {
        if (method === 'paypal') {
            method = "wallet"
        } else {
            method = method.split('paypal_').at(-1)
        }
        pretixpaypal.method = pretixpaypal.method_map[method];

        if (pretixpaypal.method.method === 'apm' && !pretixpaypal.paypage) {
            pretixpaypal.restore();
            return;
        }

        $('#paypal-button-container').empty()
        $('#paypal-card-container').empty()

        let button = pretixpaypal.paypal.Buttons({
            fundingSource: pretixpaypal.method.funding_source,
            style: {
                layout: pretixpaypal.method.early_auth ? 'horizontal' : 'vertical',
                //color: 'white',
                shape: 'rect',
                label: 'pay',
                tagline: false
            },
            createOrder: function (data, actions) {
                if (pretixpaypal.order_id) {
                    return pretixpaypal.order_id;
                }

                // On the paypal:pay view, we already pregenerated the OID.
                // Since this view is also only used for APMs, we only need the XHR-calls for the Smart Payment Buttons.
                if (pretixpaypal.paypage) {
                    return $("#payment_paypal_" + pretixpaypal.method.method + "_oid");
                } else if (window.location.pathname.endsWith("/pay/change")) {
                    let url = window.location.pathname.split('order')
                    var xhrurl = url[0] + 'paypal' + url[1].split('pay/change')[0] + 'xhr/'
                } else {
                    var xhrurl = window.location.pathname.split('checkout/')[0] + 'paypal/xhr/'
                }

                return fetch(xhrurl, {
                    method: 'POST'
                }).then(function (res) {
                    return res.json();
                }).then(function (data) {
                    return data.id;
                });
            },
            onApprove: function (data, actions) {
                waitingDialog.show(gettext("Confirming your payment …"));
                pretixpaypal.order_id = data.orderID;
                pretixpaypal.payer_id = data.payerID;

                let method = pretixpaypal.paypage ? "wallet" : pretixpaypal.method.method;
                let selectorstub = "#payment_paypal_" + method;
                var $form = $(selectorstub + "_oid").closest("form");
                // Insert the tokens into the form so it gets submitted to the server
                $(selectorstub + "_oid").val(pretixpaypal.order_id);
                $(selectorstub + "_payer").val(pretixpaypal.payer_id);
                // and submit
                $form.get(0).submit();

                // billingToken: null
                // facilitatorAccessToken: "A21AAL_fEu0gDD-sIXyOy65a6MjgSJJrhmxuPcxxUGnL5gW2DzTxiiAksfoC4x8hD-BjeY1LsFVKl7ceuO7UR1a9pQr8Q_AVw"
                // orderID: "7RF70259NY7589848"
                // payerID: "8M3BU92Z97VXA"
                // paymentID: null
            },
        });

        if (button.isEligible()) {
            button.render('#paypal-button-container');
            pretixpaypal.continue_button.hide();
        } else {
            pretixpaypal.continue_button.text(gettext('Payment method unavailable'));
            pretixpaypal.continue_button.show();
        }
    },

    renderAPMs: function () {
        pretixpaypal.restore();
        let inputselector = $("input[name=payment][value=paypal_apm]");
        // The first selector is used on the regular payment-step of the checkout flow
        // The second selector is used for the payment method change view.
        // In the long run, the layout of both pages should be adjusted to be one.
        let textselector = $("label[for=input_payment_paypal_apm]");
        let textselector2 = inputselector.next("strong");
        let eligibles = [];

        pretixpaypal.paypal.getFundingSources().forEach(function (fundingSource) {
            // Let's always skip PayPal, since it's always a dedicated funding source
            if (fundingSource === 'paypal') {
                return;
            }

            // This could also be paypal.Marks() - but they only expose images instead of cleartext...
            let button = pretixpaypal.paypal.Buttons({
                fundingSource: fundingSource
            });

            if (button.isEligible()) {
                eligibles.push(pretixpaypal.apm_map[fundingSource] || fundingSource);
            }
        });

        inputselector.attr('title', eligibles.join(', '));
        textselector.hide(1000, function () {
            textselector.text(eligibles.join(', '));
            textselector.show(1000);
        });
        textselector2.hide(1000, function () {
            textselector2[0].textContent = eligibles.join(', ');
            textselector2.show(1000);
        });
    }
};

$(function () {
    pretixpaypal.load();

    (async() => {
        while(!pretixpaypal.paypal)
            await new Promise(resolve => setTimeout(resolve, 1000));
        pretixpaypal.ready();
    })();
});
