/*global $ */

$(function () {
    window.pretix = window.pretix || {};

    var storage_key = $("#cookie-consent-storage-key").text();
    var widget_consent = $("#cookie-consent-from-widget").text();
    var consent_checkboxes = $("#cookie-consent-details input[type=checkbox][name]");
    var consent_modal = document.getElementById("cookie-consent-modal");

    function update_consent(consent, sessionOnly) {
        if (storage_key && window.sessionStorage && sessionOnly) {
            if (!window.localStorage[storage_key] || window.localStorage[storage_key] !== JSON.stringify(consent)) {
                // No need to write to sessionStorage if the value is identical to the one in localStorage
                window.sessionStorage[storage_key] = JSON.stringify(consent);
            }
        } else if (storage_key && window.localStorage) {
            window.localStorage[storage_key] = JSON.stringify(consent);
            // When saving permanent storage, clear session storage
            window.sessionStorage.removeItem(storage_key);
        }
        window.pretix.cookie_consent = consent;

        // Event() is not supported by IE11, see ployfill here:
        // https://developer.mozilla.org/en-US/docs/Web/API/CustomEvent/CustomEvent#polyfill
        var e = document.createEvent('CustomEvent');
        e.initCustomEvent('pretix:cookie-consent:change', true, true, consent);
        document.dispatchEvent(e)
    }

    if (!storage_key) {
        // We are not on a page where the consent should run, fire the change event with empty consent but don't
        // actually store anything.
        update_consent(null, false);
        return;
    }

    if (!window.localStorage) {
        // Consent not supported. Even IE8 supports it, so we're on a weird embedded device.
        // Let's just say we don't consent then.
        update_consent({}, false)
        return;
    }

    var storage_val, consent_source, save_for_session_only;
    if (window.sessionStorage[storage_key]) {
        // A manual input was given inside a widget. This is the user's last explicit choice and takes precedence –
        // as long as they are in the widget.
        storage_val = JSON.parse(window.sessionStorage[storage_key]);
        consent_source = 'sessionStorage';
        save_for_session_only = true;
    } else if (widget_consent) {
        // An input was given through the widget. This takes precedence over localStorage as we need to assume the
        // widget embedder is doing a correct job. If the user never visited the page without the widget, we also
        // use it to prefill local storage to save the user from seeing more cookie banners. (This will stop working
        // when browsers partition local storage of iframes, anyway.) If the user does have visited the page without
        // the widget before and has a consent setting in localStorage, we respect the widget consent *only* within
        // the widget -- hence, we save it into sessionStorage. We need to save it into sessionStorage because the
        // widget_data value itself will not "survive" the entire lifetime of the tab, i.e. it is no longer present
        // after the order was confirmed.
        widget_consent = JSON.parse(widget_consent);
        storage_val = {};
        consent_checkboxes.each(function () {
            this.checked = storage_val[this.name] = widget_consent.indexOf(this.name) > -1;
        });
        consent_source = 'widget';
        save_for_session_only = !!window.localStorage[storage_key];
    } else if (window.localStorage[storage_key]) {
        // The user made a specific selection, let's use that.
        storage_val = JSON.parse(window.localStorage[storage_key]) || {};
        consent_source = 'localStorage';
        save_for_session_only = false;
    } else {
        // No consent given, dialog will be shown.
        storage_val = {};
        consent_source = 'new';
        save_for_session_only = false;
    }

    var show_dialog = false;
    consent_checkboxes.each(function () {
        if (typeof storage_val[this.name] === "undefined") {
            // A new cookie type has been added that we haven't asked for yet
            if (consent_source === "widget") {
                // Trust the widget, keep it as "no consent"
            } else {
                show_dialog = true;
            }
        } else if (storage_val[this.name]) {
            this.checked = true;
        }
    })

    update_consent(storage_val, save_for_session_only);

    if (!consent_modal) {
        // Cookie consent is active, but no provider defined
        return;
    }

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
        consent_modal.showModal();
        consent_modal.addEventListener("cancel", function() {
            // Dialog was initially shown, interpret Escape as „do not consent to new providers“
            var consent = {};
            consent_checkboxes.each(function () {
                consent[this.name] = storage_val[this.name] || false;
            });
            update_consent(consent, false);
        }, {once : true});
    }

    consent_modal.addEventListener("close", function () {
        if (!consent_modal.returnValue) {// ESC, do not save
            return;
        }
        var consent = {};
        var consent_all = consent_modal.returnValue == "yes";
        consent_checkboxes.each(function () {
            consent[this.name] = this.checked = consent_all || this.checked;
        });
        if (consent_all) _set_button_text();
        update_consent(consent, false);
    });
    consent_checkboxes.on("change", _set_button_text);
    $("#cookie-consent-reopen").on("click", function (e) {
        consent_modal.showModal()
        e.preventDefault()
        return true
    })
});
