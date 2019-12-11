/*global $,gettext,ngettext */
var cart = {
    _deadline: null,
    _deadline_interval: null,
    _deadline_call: 0,
    _time_offset: 0,

    _get_now: function () {
        return moment().add(cart._time_offset, 'ms');
    },

    _calc_offset: function () {
        if (typeof window.performance === "undefined") {
            return;
        }
        var perf = window.performance.timing;
        var server_time = Math.round(parseFloat($("body").attr("data-now")) * 1000);
        // We use requestStart as we don't know how latency is distributed and we rather want to err on the safe side
        var client_time = perf.requestStart;
        cart._time_offset = server_time - client_time;
    },

    draw_deadline: function () {
        function pad(n, width, z) {
            z = z || '0';
            n = n + '';
            return n.length >= width ? n : new Array(width - n.length + 1).join(z) + n;
        }

        cart._deadline_call++;
        if ((typeof django === 'undefined' || typeof django.gettext === 'undefined') && cart._deadline_call < 5) {
            // Language files are not loaded yet, don't run during the first seconds
            return;
        }
        var now = cart._get_now();
        var diff_minutes = Math.floor(cart._deadline.diff(now) / 1000 / 60);
        var diff_seconds = Math.floor(cart._deadline.diff(now) / 1000 % 60);
        if (diff_minutes < 0) {
            $("#cart-deadline").text(gettext("The items in your cart are no longer reserved for you."));
            $("#cart-deadline-short").text(
                gettext("Cart expired")
            );
            window.clearInterval(cart._deadline_interval);
        } else {
            $("#cart-deadline").text(ngettext(
                "The items in your cart are reserved for you for one minute.",
                "The items in your cart are reserved for you for {num} minutes.",
                diff_minutes
            ).replace(/\{num\}/g, diff_minutes));
            $("#cart-deadline-short").text(
                pad(diff_minutes.toString(), 2) + ':' + pad(diff_seconds.toString(), 2)
            );
        }
    },

    init: function () {
        "use strict";
        cart._deadline = moment($("#cart-deadline").attr("data-expires"));
        cart._deadline_interval = window.setInterval(cart.draw_deadline, 500);
        cart._calc_offset();
        cart.draw_deadline();
    }
};

$(function () {
    "use strict";

    moment.locale($("body").attr("data-locale").substr(0, 2));

    if ($("#cart-deadline").length) {
        cart.init();
    }

    $(".apply-voucher").hide();
    $(".apply-voucher-toggle").click(function (e) {
        $(".apply-voucher-toggle").hide();
        $(".apply-voucher").show();
        $(".apply-voucher input[ŧype=text]").first().focus();
        e.preventDefault();
        return true;
    });
});
