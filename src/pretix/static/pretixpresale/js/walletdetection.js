'use strict';

var walletdetection = {
    applepay: async function () {
        // This is a weak check for Apple Pay -  in order to do a proper check, we would need to also call
        // canMakePaymentsWithActiveCard(merchantIdentifier)

        return !!(window.ApplePaySession && window.ApplePaySession.canMakePayments());
    },
    googlepay: async function () {
        // Checking for Google Pay is a little bit more involved, since it requires including the Google Pay JS SDK, and
        // providing a lot of information.
        // So for the time being, we only check if Google Pay is available in TEST-mode, which should hopefully give us a
        // good enough idea if Google Pay could be present on this device; even though there are still a lot of other
        // factors that could inhibit Google Pay from actually being offered to the customer.

        return $.ajax({
            url: 'https://pay.google.com/gp/p/js/pay.js',
            dataType: 'script',
        }).then(function() {
            const paymentsClient = new google.payments.api.PaymentsClient({environment: 'TEST'});
            return paymentsClient.isReadyToPay({
                apiVersion: 2,
                apiVersionMinor: 0,
                allowedPaymentMethods: [{
                    type: 'CARD',
                    parameters: {
                        allowedAuthMethods: ["PAN_ONLY", "CRYPTOGRAM_3DS"],
                        allowedCardNetworks: ["AMEX", "DISCOVER", "INTERAC", "JCB", "MASTERCARD", "VISA"]
                    }
                }],
            })
        }).then(function (response) {
            return !!response.result;
        });
    },
    name_map: {
        applepay: gettext('Apple Pay'),
        googlepay: gettext('Google Pay'),
    }
}

$(function () {
    const wallets = $('[data-wallets]')
        .map(function(index, pm) {
            return pm.getAttribute("data-wallets").split("|");
        })
        .get()
        .flat()
        .filter(function(item, pos, self) {
            // filter out empty or duplicate values
            return item && self.indexOf(item) == pos;
        });

    wallets.forEach(function(wallet) {
        const labels = $('[data-wallets*='+wallet+'] + label strong, [data-wallets*='+wallet+'] + strong')
            .append('<span class="wallet wallet-loading"> <i aria-hidden="true" class="fa fa-cog fa-spin"></i></span>')
        walletdetection[wallet]()
            .then(function(result) {
                const spans = labels.find(".wallet-loading:nth-of-type(1)");
                if (result) {
                    spans.removeClass('wallet-loading').hide().text(', ' + walletdetection.name_map[wallet]).fadeIn(300);
                } else {
                    spans.remove();
                }
            })
            .catch(function(result) {
                labels.find(".wallet-loading:nth-of-type(1)").remove();
            })
    });
});
