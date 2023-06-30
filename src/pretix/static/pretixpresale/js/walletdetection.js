'use strict';

var walletdetection = {
    applepay: function () {
        // This is a weak check for Apple Pay -  in order to do a proper check, we would need to also call
        // canMakePaymentsWithActiveCard(merchantIdentifier)

        return !!(window.ApplePaySession && window.ApplePaySession.canMakePayments());
    },
    googlepay: function () {
        // Checking for Google Pay is a little bit more involved, since it requires including the Google Pay JS SDK, and
        // providing a lot of information.
        // So for the time being, we only check if Google Pay is available in TEST-mode, which should hopefully give us a
        // good enough idea if Google Pay could be present on this device; even though there are still a lot of other
        // factors that could inhibit Google Pay from actually being offered to the customer.

        const baseRequest = {
            apiVersion: 2,
            apiVersionMinor: 0
        };
        const tokenizationSpecification = {
            type: 'PAYMENT_GATEWAY',
            parameters: {
                'gateway': 'example',
                'gatewayMerchantId': 'exampleGatewayMerchantId'
            }
        };
        const allowedCardNetworks = ["AMEX", "DISCOVER", "INTERAC", "JCB", "MASTERCARD", "VISA"];
        const allowedCardAuthMethods = ["PAN_ONLY", "CRYPTOGRAM_3DS"];
        const baseCardPaymentMethod = {
            type: 'CARD',
            parameters: {
                allowedAuthMethods: allowedCardAuthMethods,
                allowedCardNetworks: allowedCardNetworks
            }
        };
        const cardPaymentMethod = Object.assign(
            {tokenizationSpecification: tokenizationSpecification},
            baseCardPaymentMethod
        );

        return $.ajax({
            url: 'https://pay.google.com/gp/p/js/pay.js',
            dataType: 'script',
            success: function () {
                const paymentsClient = new google.payments.api.PaymentsClient({environment: 'TEST'});
                const isReadyToPayRequest = Object.assign({}, baseRequest);
                isReadyToPayRequest.allowedPaymentMethods = [baseCardPaymentMethod];

                paymentsClient.isReadyToPay(isReadyToPayRequest)
                    .then(function (response) {
                        if (response.result) {
                            return true;
                        }
                    })
                    .catch(function (err) {
                        return false;
                    });
            },
        });
    },
    name_map: {
        applepay: gettext('Apple Pay'),
        googlepay: gettext('Google Pay'),
    }
}

$(function () {
    let requestedWallets = Array();
    let paymentMethods = $('[data-wallets][data-wallets!=""]');

    paymentMethods.each(function () {
        let $s = $(this);
        requestedWallets = requestedWallets.concat($s.data("wallets").split("|"));
    })

    // Filtering out any doubles
    requestedWallets = new Set(requestedWallets);

    // Perform the actual check *only* on the requested wallets, if they are supported by the browser
    let availableWallets = Array();
    requestedWallets.forEach(function (it) {
        if (walletdetection[it]()) {
            availableWallets.push(it);
        }
    });

    paymentMethods.each(function () {
        let $s = $(this);
        let wallets = Array();

        // Run the translation on the available wallet strings before pushing them out.
        $s.data("wallets").split("|").forEach(function (it) {
            if (availableWallets.includes(it)) {
                wallets.push(gettext(walletdetection.name_map[it]));
            }
        })

        // In case there is no wallets available, we do not want to flicker the screen
        if (wallets.length === 0) {
            return;
        }

        // The first selector is used on the regular payment-step of the checkout flow
        // The second selector is used for the payment method change view.
        // In the long run, the layout of both pages should be adjusted to be one.
        let textselector = $s.next('label').find('strong');
        let textselector2 = $s.next("strong");
        textselector.fadeOut(300, function () {
            wallets.unshift(textselector.text());
            textselector.text(wallets.join(", "));
            textselector.fadeIn(300);
        });
        textselector2.fadeOut(300, function () {
            wallets.unshift(textselector2.text());
            textselector2.text(wallets.join(", "));
            textselector2.fadeIn(300);
        });
    });
});