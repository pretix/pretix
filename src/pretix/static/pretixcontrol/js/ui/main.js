/*global $,gettext*/

function question_page_toggle_view() {
    var show = $("#id_type").val() == "C" || $("#id_type").val() == "M";
    $("#answer-options").toggle(show);

    show = $("#id_type").val() == "B" && $("#id_required").prop("checked");
    $(".alert-required-boolean").toggle(show);
}

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

var ajaxErrDialog = {
    show: function (c) {
        "use strict";
        $("#ajaxerr").html(c);
        $("#ajaxerr .links").html("<a class='btn btn-default ajaxerr-close'>"
                                  + gettext("Close message") + "</a>");
        $("body").addClass("ajaxerr");
    },
    hide: function () {
        "use strict";
        $("body").removeClass("ajaxerr");
    }
};

$(document).ajaxError(function (event, jqXHR, settings, thrownError) {
    waitingDialog.hide();
    var c = $(jqXHR.responseText).filter('.container');
    if (c.length > 0) {
        ajaxErrDialog.show(c.first().html());
    } else {
        alert(gettext('Unknown error.'));
    }
});

$(function () {
    "use strict";

    $("[data-formset]").formset(
        {
            animateForms: true,
            reorderMode: 'animate'
        }
    );
    $(document).on("click", ".variations .variations-select-all", function (e) {
        $(this).parent().parent().find("input[type=checkbox]").prop("checked", true).change();
        e.stopPropagation();
        return false;
    });
    $(document).on("click", ".variations .variations-select-none", function (e) {
        $(this).parent().parent().find("input[type=checkbox]").prop("checked", false).change();
        e.stopPropagation();
        return false;
    });
    if ($(".items-on-quota").length) {
        $(".items-on-quota .panel").each(function () {
            var $panel = $(this);
            $panel.toggleClass("panel-success", $panel.find("input:checked").length > 0);
            $(this).find("input").change(function () {
                $panel.toggleClass("panel-success", $panel.find("input:checked").length > 0);
            });
        });
    }

    $("#sumtoggle").find("button").click(function () {
        $(".table-product-overview .sum-gross").toggle($(this).attr("data-target") === ".sum-gross");
        $(".table-product-overview .sum-net").toggle($(this).attr("data-target") === ".sum-net");
        $(".table-product-overview .count").toggle($(this).attr("data-target") === ".count");

        $("#sumtoggle").find("button").not($(this)).removeClass("active");
        $(this).addClass("active");
    });

    $('.collapsible').collapse();
    
    $('[data-toggle="tooltip"]').tooltip();

    var url = document.location.toString();
    if (url.match('#')) {
        $('.nav-tabs a[href="#' + url.split('#')[1] + '"]').tab('show');
    }
    $('a[data-toggle="tab"]').on('click', function (e) {
        window.location.hash = e.target.hash;
    });

    // Question editor
    if ($("#answer-options").length) {

        $("#id_type").change(question_page_toggle_view);
        $("#id_required").change(question_page_toggle_view);
        question_page_toggle_view();
    }

    // Vouchers
    $("#voucher-bulk-codes-generate").click(function () {
        var num = $("#voucher-bulk-codes-num").val();
        if (num != "") {
            $(".form-group:has(#voucher-bulk-codes-num)").addClass("has-error");
            var url = $(this).attr("data-rng-url");
            $("#id_codes").html("Generating...");
            $.getJSON(url + '?num=' + num, function (data) {
                $("#id_codes").val(data.codes.join("\n"));
            });
        } else {
            $(".form-group:has(#voucher-bulk-codes-num)").addClass("has-error");
            $("#voucher-bulk-codes-num").focus();
            setTimeout(function() {
                $(".form-group:has(#voucher-bulk-codes-num)").removeClass("has-error");
            }, 3000);
        }
    });

    $("#ajaxerr").on("click", ".ajaxerr-close", ajaxErrDialog.hide);

    $(".datetimepicker").each(function() {
        $(this).datetimepicker({
            format: $("body").attr("data-datetimeformat"),
            locale: $("body").attr("data-datetimelocale"),
            useCurrent: false,
            showClear: !$(this).prop("required"),
            icons: {
                time: 'fa fa-clock-o',
                date: 'fa fa-calendar',
                up: 'fa fa-chevron-up',
                down: 'fa fa-chevron-down',
                previous: 'fa fa-chevron-left',
                next: 'fa fa-chevron-right',
                today: 'fa fa-screenshot',
                clear: 'fa fa-trash',
                close: 'fa fa-remove'
            }
        });
    });

    $(".datepickerfield").each(function() {
        var opts = {
            format: $("body").attr("data-dateformat"),
            locale: $("body").attr("data-datetimelocale"),
            useCurrent: false,
            showClear: !$(this).prop("required"),
            icons: {
                time: 'fa fa-clock-o',
                date: 'fa fa-calendar',
                up: 'fa fa-chevron-up',
                down: 'fa fa-chevron-down',
                previous: 'fa fa-chevron-left',
                next: 'fa fa-chevron-right',
                today: 'fa fa-screenshot',
                clear: 'fa fa-trash',
                close: 'fa fa-remove'
            }
        };
        if ($(this).is('[data-is-payment-date]'))
            opts["daysOfWeekDisabled"] = JSON.parse($("body").attr("data-payment-weekdays-disabled"));
        $(this).datetimepicker(opts);
    });

    $(".qrcode-canvas").each(function() {
        $(this).qrcode(
            {
                text: $.trim($($(this).attr("data-qrdata")).html())
            }
        );
    });
});
