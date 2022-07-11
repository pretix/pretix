/*global $ */

$(function () {
    var popup_window = null
    var popup_check_interval = null

    $("#popupmodal").removeAttr("hidden");

    $("a[data-open-in-popup-window]").on("click", function (e) {
        e.preventDefault()

        $("#popupmodal a").attr("href", this.href)

        var url = this.href
        if (url.includes("?")) {
            url += "&popup_origin=" + window.location.origin
        } else {
            url += "?popup_origin=" + window.location.origin
        }
        popup_window = window.open(
            url,
            "presale-popup",
            "scrollbars=yes,resizable=yes,status=yes,location=yes,toolbar=no,menubar=no,width=940,height=620,left=50,top=50"
        )
        $("body").addClass("has-popup")

        popup_check_interval = window.setInterval(function () {
            if (popup_window.closed) {
                $("body").removeClass("has-popup")
                window.clearInterval(popup_check_interval)
            }
        }, 250)

        return false
    });

    window.addEventListener("message", function (event) {
        if (event.source !== popup_window)
            return
        if (event.data && event.data.__process === "customer_sso_popup") {
            if (event.data.status === "ok") {
                $("#login_sso_data").val(event.data.value)
                $("#login_sso_data").closest("form").get(0).submit()
            } else {
                alert(event.data.value)  // todo
            }
            event.source.postMessage({'__process': 'popup_close'}, "*")
        }
        console.log(event)
    }, false);
})