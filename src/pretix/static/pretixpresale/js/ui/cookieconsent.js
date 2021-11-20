/*global $ */

$(function () {
    function _send_event(type) {
        // Event() is not supported by IE11
        var e = document.createEvent('Event')
        e.initEvent(type, true, true)
        document.dispatchEvent(e)
    }

    if ($("#cookie-consent-storage-key").length) {
        window.__pretix_cookie_consent = {}
    } else {
        window.__pretix_cookie_consent = null
        return
    }

    var storage_key = $("#cookie-consent-storage-key").text()
    var storage_val = window.localStorage[storage_key]
    var show_dialog = false
    if (!storage_val) {
        show_dialog = true
        storage_val = {}

        if ($("#cookie-consent-from-widget").length) {
            var consented = JSON.parse($("#cookie-consent-from-widget").text())
            $("#cookie-consent-details input[type=checkbox][name]").each(function () {
                storage_val[$(this).attr("name")] = consented.indexOf($(this).attr("name")) > -1
                $(this).prop("checked", consented.indexOf($(this).attr("name")) > -1)
            })
            window.localStorage[storage_key] = JSON.stringify(storage_val)
            show_dialog = false
        }
    } else {
        storage_val = JSON.parse(storage_val)
        $("#cookie-consent-details input[type=checkbox][name]").each(function () {
            if (typeof storage_val[$(this).attr("name")] === "undefined") {
                // A new cookie type has been added that we haven't asked for yet
                show_dialog = true
            } else if (storage_val[$(this).attr("name")]) {
                $(this).prop("checked", true)
            }
        })
    }
    window.__pretix_cookie_consent = storage_val
    _send_event('pretix:cookie-consent-updated')

    function _set_button_text () {
        if ($("#cookie-consent-details input[type=checkbox][name]:checked").length > 0) {
            $("#cookie-consent-button-no").text(
                $("#cookie-consent-button-no").attr("data-detail-text")
            )
        } else {
            $("#cookie-consent-button-no").text(
                $("#cookie-consent-button-no").attr("data-summary-text")
            )
        }
    }

    var n_checked = $("#cookie-consent-details input[type=checkbox][name]:checked").length
    var n_total = $("#cookie-consent-details input[type=checkbox][name]").length
    if (n_checked !== n_total && n_checked !== 0) {
        $("#cookie-consent-details").prop("open", true)
        $("#cookie-consent-details > *:not(summary)").show()
    }

    _set_button_text()
    if (show_dialog) {
        // We use .css() instead of .show() because of some weird issue that only occurs in Firefox
        // and only within the widget.
        $("#cookie-consent-modal").css("display", "block");
    }

    $("#cookie-consent-button-yes").on("click", function () {
        var new_value = {}
        $("#cookie-consent-details input[type=checkbox][name]").each(function () {
            new_value[$(this).attr("name")] = true
            $(this).prop("checked", true)
        })

        window.localStorage[storage_key] = JSON.stringify(new_value)
        window.__pretix_cookie_consent = new_value
        _send_event('pretix:cookie-consent-updated')
        $("#cookie-consent-modal").hide()
    })
    $("#cookie-consent-button-no").on("click", function () {
        var new_value = {}
        $("#cookie-consent-details input[type=checkbox][name]").each(function () {
            new_value[$(this).attr("name")] = $(this).prop("checked")
        })

        window.localStorage[storage_key] = JSON.stringify(new_value)
        window.__pretix_cookie_consent = new_value
        _send_event('pretix:cookie-consent-updated')
        $("#cookie-consent-modal").hide()
    })
    $("#cookie-consent-details input").on("change", _set_button_text)
    $("#cookie-consent-reopen").on("click", function (e) {
        $("#cookie-consent-modal").show()
        e.preventDefault()
        return true
    })
});
