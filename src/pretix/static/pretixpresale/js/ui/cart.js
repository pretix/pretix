/*global $,gettext,ngettext */

var cart = {
    _deadline: null,
    _deadline_interval: null,

    draw_deadline: function () {
        var diff = Math.floor(cart._deadline.diff(moment()) / 1000 / 60);
        if (diff < 0) {
            $("#cart-deadline").text(gettext("The items in your cart are no longer reserved for you."));
            window.clearInterval(cart._deadline_interval);
        } else {
            $("#cart-deadline").text(ngettext(
                "The items in your cart are reserved for you for one minute.",
                "The items in your cart are reserved for you for {num} minutes.",
                diff
            ).replace(/\{num\}/g, diff));
        }
    },

    init: function () {
        "use strict";
        cart._deadline = moment($("#cart-deadline").attr("data-expires"));
        cart._deadline_interval = window.setInterval(cart.draw_deadline, 2000);
        cart.draw_deadline();
    }
};

$(function () {
    "use strict";

    moment.locale($("body").attr("data-locale").substr(0, 2));

    if ($("#cart-deadline").length) {
        cart.init();
    }
});
