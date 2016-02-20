/*global $ */

$(function () {
    "use strict";
    $("input[data-toggle=radiocollapse]").change(function () {
        $($(this).attr("data-parent")).find(".collapse.in").collapse('hide');
        $($(this).attr("data-target")).collapse('show');
    });
    $(".js-only").removeClass("js-only");
    $(".variations").hide();
    $("a[data-toggle=variations]").click(function () {
        $(this).parent().parent().parent().find(".variations").slideToggle();
    });
    $(".collapsed").removeClass("collapsed").addClass("collapse");

    $("#voucher-box").hide();
    $("#voucher-toggle").show();
    $("#voucher-toggle a").click(function () {
        $("#voucher-box").slideDown();
        $("#voucher-toggle").slideUp();
    });
});

var waitingDialog = {
    show: function (message) {
        "use strict";
        $("#loadingmodal").find("h1").html(message);
        $("body").addClass("loading");
    },
    hide: function () {
        "use strict";
        $("body").removeClass("loading");
    }
};
