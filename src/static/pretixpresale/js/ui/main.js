"use strict";

$(function () {
    $("input[data-toggle=radiocollapse]").change(function () {
        $($(this).attr("data-parent")).find(".collapse.in").collapse('hide');
        $($(this).attr("data-target")).collapse('show');
    });
    $(".js-only").removeClass("js-only");
    $(".variations").hide();
    $("a[data-toggle=variations]").click(function() {
        $(this).parent().parent().parent().find(".variations").slideToggle();
    });
    $(".collapsed").removeClass("collapsed").addClass("collapse");
});

var waitingDialog = (function ($) {

    return {
        show: function (message, options) {
            $("#loadingmodal h1").html(message);
            $("body").addClass("loading");
        },
        hide: function () {
            $("body").removeClass("loading");
        }
    }

})(jQuery);
