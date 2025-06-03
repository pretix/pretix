/*global $,gettext,ngettext */
var cart = {
    _deadline: null,
    _deadline_timeout: null,
    _deadline_call: 0,
    _time_offset: 0,
    _prev_diff_minutes: 0,

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

    show_expiry_notification: function () {
        document.getElementById("dialog-cart-extend").showModal();
        cart._expiry_notified = true;
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
        var diff_total_seconds = cart._deadline.diff(now) / 1000;
        var diff_minutes = Math.floor(diff_total_seconds / 60);
        var diff_seconds = Math.floor(diff_total_seconds % 60);

        if (diff_minutes < 0) {
            $("#cart-deadline").text(gettext("The items in your cart are no longer reserved for you. You can still complete your order as long as they’re available."));
            $("#cart-deadline-short").text(
                gettext("Cart expired")
            );
            if (!cart._deadline_timeout) {
                // no timeout => first time draw_deadline is invoked, but cart already expired => do not show dialog
                cart._expiry_notified = true;
            }
        } else {
            if (diff_minutes !== cart._prev_diff_minutes) {
                if (diff_minutes == 0) {
                    $("#cart-deadline").text(gettext("Your cart is about to expire."))
                } else {
                    $("#cart-deadline").text(
                        ngettext(
                            "The items in your cart are reserved for you for one minute.",
                            "The items in your cart are reserved for you for {num} minutes.",
                            diff_minutes
                        ).replace(/\{num\}/g, diff_minutes)
                    );
                }
                cart._prev_diff_minutes = diff_minutes;
            }

            $("#cart-deadline-short").text(
                pad(diff_minutes.toString(), 2) + ':' + pad(diff_seconds.toString(), 2)
            );

            cart._deadline_timeout = window.setTimeout(cart.draw_deadline, 500);
        }
        var already_expired = diff_total_seconds <= 0;
        var can_extend_cart = diff_minutes < 3 && (already_expired || cart._deadline < cart._max_extend);
        $("#cart-extend-button").toggle(can_extend_cart);
        if (can_extend_cart && diff_total_seconds < 45) {
            if (!cart._expiry_notified) cart.show_expiry_notification();
            $("#dialog-cart-extend-title").text(already_expired
                ? gettext("Your cart has expired.")
                : gettext("Your cart is about to expire."));
            $("#dialog-cart-extend-description").text(already_expired
                ? gettext("The items in your cart are no longer reserved for you. You can still complete your order as long as they're available.")
                : gettext("Do you want to renew the reservation period?"));
            $("#dialog-cart-extend .modal-card-confirm button").text(already_expired
                ? gettext("Continue")
                : gettext("Renew reservation"));
        }
    },

    init: function () {
        "use strict";
        cart._calc_offset();
        cart.set_deadline(
            $("#cart-deadline").attr("data-expires"),
            $("#cart-deadline").attr("data-max-expiry-extend")
        );
    },

    set_deadline: function (expiry, max_extend, renewed_message) {
        "use strict";
        cart._expiry_notified = false;
        cart._deadline = moment(expiry);
        if (cart._deadline_timeout) {
            window.clearTimeout(cart._deadline_timeout);
        }
        cart._deadline_timeout = null;
        cart._max_extend = moment(max_extend);
        cart.draw_deadline();
    }
};

$(function () {
    "use strict";

    if ($("#cart-deadline").length) {
        cart.init();
        $("#cart-extend-confirmation-button").hide().on("blur", function() {
            $(this).hide();
        });
    }

    $("#cart-extend-form").on("pretix:async-task-success", function(e, data) {
        if (data.success) {
            cart.set_deadline(data.expiry, data.max_expiry_extend);
        } else {
            alert(data.message);
        }
    });
    // renew-button in cart-panel is clicked, show inline dialog
    $("#cart-extend-button").on("click", function() {
        $("#cart-extend-form").one("pretix:async-task-success", function(e, data) {
            if (data.success) {
                document.getElementById("cart-extend-confirmation-dialog").show();
            }
        });
    });
    $("#cart-extend-confirmation-dialog").on("keydown", function (e) {
        if(e.key === "Escape") {
            this.close();
        }
    });

    // renew-button in modal dialog is clicked, show modal dialog
    $("#dialog-cart-extend form").submit(function() {
        $("#cart-extend-form").one("pretix:async-task-success", function(e, data) {
            if (data.success) {
                $("#dialog-cart-extended-title").text(data.message);
                $("#dialog-cart-extended-description").text($("#cart-deadline").text());
                document.getElementById("dialog-cart-extended").showModal();
            }
        }).submit();
    });

    $(".toggle-container").each(function() {
        var summary = $(".toggle-summary", this);
        var content = $("> :not(.toggle-summary)", this);
        var toggle  = summary.find(".toggle").on("click", function(e) {
            this.ariaExpanded = !this.ariaExpanded;
            if (this.classList.contains("toggle-remove")) summary.attr("hidden", true);
            content.show().find(":input:visible").first().focus();
        });
        if (toggle.attr("aria-expanded")) {
            content.hide();
        }
    });

    $(".cart-icon-details.collapse-lines").each(function () {
        var $content = $(this).find(".content");
        var original_html = $content.html();
        var br_exp = /<br\s*\/?>/i;
        $content.text(original_html.split(br_exp).join(', '));
        if ($content.get(0).scrollWidth > $content.get(0).offsetWidth) {
            var $handler = $("<button>")
                .text($(this).attr("data-expand-text"))
                .addClass("btn btn-link collapse-handler")
                .attr("type", "button")
                .attr("aria-controls", $content.attr('id'))
                .attr("aria-expanded", "false");
            $handler.on("click", function (ev) {
                $content.html(original_html).removeClass("content");
                $handler.attr("aria-expanded", "true").attr("aria-hidden", "true");
                $handler.hide();
            });
            $(this).append($handler);
        }
    })
});
