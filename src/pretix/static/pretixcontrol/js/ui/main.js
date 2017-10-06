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
    $(".has-error").each(function () {
        $(this).closest("div.panel-collapse").collapse("show");
    });

    $('[data-toggle="tooltip"]').tooltip();
    $('[data-toggle="tooltip_html"]').tooltip({
        'html': true
    });

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

    // Event wizard
    $("#event-slug-random-generate").click(function () {
        var url = $(this).attr("data-rng-url");
        $("#id_basics-slug").val("Generating...");
        $.getJSON(url, function (data) {
            $("#id_basics-slug").val(data.slug);
        });
    });

    // Vouchers
    $("#voucher-bulk-codes-generate").click(function () {
        var num = $("#voucher-bulk-codes-num").val();
        var prefix = $('#voucher-bulk-codes-prefix').val();
        if (num != "") {
            var url = $(this).attr("data-rng-url");
            $("#id_codes").html("Generating...");
            $(".form-group:has(#voucher-bulk-codes-num)").removeClass("has-error");
            $.getJSON(url + '?num=' + num + '&prefix=' + escape(prefix), function (data) {
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
    moment.locale($("body").attr("data-datetimelocale"));

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
        if (!$(this).val()) {
            $(this).data("DateTimePicker").viewDate(moment().hour(0).minute(0).second(0));
        }
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
            },
        };
        if ($(this).is('[data-is-payment-date]'))
            opts["daysOfWeekDisabled"] = JSON.parse($("body").attr("data-payment-weekdays-disabled"));
        $(this).datetimepicker(opts);
        if ($(this).parent().is('.splitdatetimerow')) {
            $(this).on("dp.change", function (ev) {
                var $timepicker = $(this).closest(".splitdatetimerow").find(".timepickerfield");
                var date = $(this).data('DateTimePicker').date();
                if (date === null) {
                    return;
                }
                date.set({'hour': 0, 'minute': 0, 'second': 0});
                $timepicker.data('DateTimePicker').date(date);
            });
        }
    });

    $(".timepickerfield").each(function() {
        var opts = {
            format: $("body").attr("data-timeformat"),
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

    $(".datetimepicker[data-date-after], .datepickerfield[data-date-after]").each(function() {
        var later_field = $(this),
            earlier_field = $($(this).attr("data-date-after")),
            update = function () {
                var earlier = earlier_field.data('DateTimePicker').date(),
                    later = later_field.data('DateTimePicker').date();
                if (earlier === null) {
                    earlier = false;
                } else if (later !== null && later.isBefore(earlier) && !later.isSame(earlier)) {
                    later_field.data('DateTimePicker').date(earlier.add(1, 'h'));
                }
                later_field.data('DateTimePicker').minDate(earlier);
            };
        update();
        earlier_field.on("dp.change", update);
    });

    $(".datetimepicker[data-date-default]").each(function() {
        var fill_field = $(this),
            default_field = $($(this).attr("data-date-default")),
            show = function () {
                var fill_date = fill_field.data('DateTimePicker').date(),
                    default_date = default_field.data('DateTimePicker').date();
                if (fill_date === null) {
                    fill_field.data("DateTimePicker").defaultDate(default_date);
                }
            };
        fill_field.on("dp.show", show);
    });

    $(".colorpickerfield").colorpicker({
        format: 'hex',
        align: 'left',
        customClass: 'colorpicker-2x',
        sliders: {
            saturation: {
                maxLeft: 200,
                maxTop: 200
            },
            hue: {
                maxTop: 200
            },
            alpha: {
                maxTop: 200
            }
        }
    });

    $("input[data-checkbox-dependency]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-checkbox-dependency")),
            update = function () {
                var enabled = dependency.prop('checked');
                dependent.prop('disabled', !enabled).parents('.form-group').toggleClass('disabled', !enabled);
                if (!enabled) {
                    dependent.prop('checked', false);
                }
            };
        update();
        dependency.on("change", update);
    });

    $("input[data-inverse-dependency]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-inverse-dependency")),
            update = function () {
                var enabled = !dependency.prop('checked');
                dependent.prop('disabled', !enabled).parents('.form-group').toggleClass('disabled', !enabled);
            };
        update();
        dependency.on("change", update);
    });

    $("input[data-display-dependency]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-display-dependency")),
            update = function () {
                var enabled = (dependency.attr("type") === 'checkbox') ? dependency.prop('checked') : !!dependency.val();
                dependent.prop('disabled', !enabled).parents('.form-group').toggleClass('disabled', !enabled);
            };
        update();
        dependency.on("change", update);
        dependency.on("dp.change", update);
    });

    $(".qrcode-canvas").each(function() {
        $(this).qrcode(
            {
                text: $.trim($($(this).attr("data-qrdata")).html())
            }
        );
    });

    $(".propagated-settings-box button[data-action=unlink]").click(function(ev) {
        var $box = $(this).closest(".propagated-settings-box");
        $box.find(".propagated-settings-overlay").fadeOut();
        $box.find("input[name=_settings_ignore]").attr("name", "decouple");
        $box.find(".propagated-settings-form").removeClass("blurred");
        ev.preventDefault();
        return true;
    })
});
