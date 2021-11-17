/*global $ */

window.__pretix_cookie_update_listeners = window.__pretix_cookie_update_listeners || []

$(function () {
    var storage_key = $("#cookie-consent-storage-key").text()
    var storage_val = window.localStorage[storage_key]
    var show_dialog = false
    if (!storage_val) {
        show_dialog = true
        storage_val = {}
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
        $("#cookie-consent-modal").show();
    }

    $("#cookie-consent-button-yes").on("click", function () {
        var new_value = {}
        $("#cookie-consent-details input[type=checkbox][name]").each(function () {
            new_value[$(this).attr("name")] = true
            $(this).prop("checked", true)
        })

        window.localStorage[storage_key] = JSON.stringify(new_value)
        for (var k of window.__pretix_cookie_update_listeners) {
            k.call(this, window.localStorage[storage_key])
        }
        $("#cookie-consent-modal").hide()
    })
    $("#cookie-consent-button-no").on("click", function () {
        var new_value = {}
        $("#cookie-consent-details input[type=checkbox][name]").each(function () {
            new_value[$(this).attr("name")] = $(this).prop("checked")
        })

        window.localStorage[storage_key] = JSON.stringify(new_value)
        for (var k of window.__pretix_cookie_update_listeners) {
            k.call(this, window.localStorage[storage_key])
        }
        $("#cookie-consent-modal").hide()
    })
    $("#cookie-consent-details input").on("change", _set_button_text)
    $("#cookie-consent-reopen").on("click", function (e) {
        $("#cookie-consent-modal").show()
        e.preventDefault()
        return true
    })
});
