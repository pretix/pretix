/*global $ */

$(function () {
    window.pretix = window.pretix || {};

    var storage_key = $("#cookie-consent-storage-key").text();
    function update_consent(consent) {
        if (storage_key && window.localStorage) window.localStorage[storage_key] = JSON.stringify(consent);
        window.pretix.cookie_consent = consent;

        // Event() is not supported by IE11, see ployfill here:
        // https://developer.mozilla.org/en-US/docs/Web/API/CustomEvent/CustomEvent#polyfill
        var e = document.createEvent('CustomEvent');
        e.initCustomEvent('pretix:cookie-consent:change', true, true, consent);
        document.dispatchEvent(e)
    }

    if (!storage_key) {
        update_consent(null);
        return;
    }

    if (!window.localStorage) {
        // Consent not supported. Even IE8 supports it, so we're on a weird embedded device.
        // Let's just say we don't consent then.
        update_consent({})
        return;
    }

    var storage_val = window.localStorage[storage_key];
    var show_dialog = !storage_val;
    var consent_checkboxes = $("#cookie-consent-details input[type=checkbox][name]");
    var consent_modal = $("#cookie-consent-modal");
    if (storage_val) {
        storage_val = JSON.parse(storage_val);
        consent_checkboxes.each(function () {
            if (typeof storage_val[this.name] === "undefined") {
                // A new cookie type has been added that we haven't asked for yet
                show_dialog = true;
            } else if (storage_val[this.name]) {
                this.checked = true;
            }
        })
    } else {
        storage_val = {}
        var consented = $("#cookie-consent-from-widget").text();
        if (consented) {
            consented = JSON.parse(consented);
            consent_checkboxes.each(function () {
                this.checked = storage_val[this.name] = consented.indexOf(this.name) > -1;
            })
            show_dialog = false
        }
    }
    update_consent(storage_val);

    function _set_button_text () {
        var btn = $("#cookie-consent-button-no");
        btn.text(
            consent_checkboxes.filter(":checked").length ?
            btn.attr("data-detail-text") : 
            btn.attr("data-summary-text")
        );
    }

    if (consent_checkboxes.filter(":checked").length) {
        $("#cookie-consent-details").prop("open", true).find("> *:not(summary)").show();
    }

    _set_button_text();
    if (show_dialog) {
        // We use .css() instead of .show() because of some weird issue that only occurs in Firefox
        // and only within the widget.
        consent_modal.css("display", "block");
    }

    $("#cookie-consent-button-yes, #cookie-consent-button-no").on("click", function () {
        consent_modal.hide();
        var consent = {};
        var consent_all = this.id == "cookie-consent-button-yes";
        consent_checkboxes.each(function () {
            consent[this.name] = this.checked = consent_all || this.checked;
        });
        if (consent_all) _set_button_text();
        update_consent(consent);
    });
    consent_checkboxes.on("change", _set_button_text);
    $("#cookie-consent-reopen").on("click", function (e) {
        consent_modal.show()
        e.preventDefault()
        return true
    })
});
