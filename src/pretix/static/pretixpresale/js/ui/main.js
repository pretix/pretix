/*global $ */

function gettext(msgid) {
    if (typeof django !== 'undefined' && typeof django.gettext !== 'undefined') {
        return django.gettext(msgid);
    }
    return msgid;
}

function ngettext(singular, plural, count) {
    if (typeof django !== 'undefined' && typeof django.ngettext !== 'undefined') {
        return django.ngettext(singular, plural, count);
    }
    return plural;
}

var form_handlers = function (el) {
    el.find(".datetimepicker").each(function () {
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

    el.find(".datepickerfield").each(function () {
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
        $(this).datetimepicker(opts);
        if ($(this).parent().is('.splitdatetimerow')) {
            $(this).on("dp.change", function (ev) {
                var $timepicker = $(this).closest(".splitdatetimerow").find(".timepickerfield");
                var date = $(this).data('DateTimePicker').date();
                if (date === null) {
                    return;
                }
                if ($timepicker.val() === "") {
                    date.set({'hour': 0, 'minute': 0, 'second': 0});
                    $timepicker.data('DateTimePicker').date(date);
                }
            });
        }
    });

    el.find(".timepickerfield").each(function () {
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
        $(this).datetimepicker(opts);
    });

    el.find("script[data-replace-with-qr]").each(function () {
        var $div = $("<div>");
        $div.insertBefore($(this));
        $div.qrcode(
            {
                text: $(this).html(),
                correctLevel: 0,  // M
                width: $(this).attr("data-size") ? parseInt($(this).attr("data-size")) : 256,
                height: $(this).attr("data-size") ? parseInt($(this).attr("data-size")) : 256,
            }
        );
    });

    el.find("input[name*=question], select[name*=question]").change(questions_toggle_dependent);
    questions_toggle_dependent();
};


$(function () {
    "use strict";

    $("body").removeClass("nojs");

    $("input[data-toggle=radiocollapse]").change(function () {
        $($(this).attr("data-parent")).find(".collapse.in").collapse('hide');
        $($(this).attr("data-target")).collapse('show');
    });
    $(".js-only").removeClass("js-only");
    $(".js-hidden").hide();

    $("div.collapsed").removeClass("collapsed").addClass("collapse");
    $(".has-error, .alert-danger").each(function () {
        $(this).closest("div.panel-collapse").collapse("show");
    });

    $("#voucher-box").hide();
    $("#voucher-toggle").show();
    $("#voucher-toggle a").click(function () {
        $("#voucher-box").slideDown();
        $("#voucher-toggle").slideUp();
    });

    $('[data-toggle="tooltip"]').tooltip();

    $("#ajaxerr").on("click", ".ajaxerr-close", ajaxErrDialog.hide);

    // AddOns
    $('.addon-variation-description').hide();
    $('.toggle-variation-description').click(function () {
        $(this).parent().find('.addon-variation-description').slideToggle();
    });

    // Copy answers
    $(".js-copy-answers").click(function (e) {
        e.preventDefault();
        e.stopPropagation();
        var idx = $(this).data('id');
        copy_answers(idx);
        return false;
    });
    var copy_to_first_ticket = true;
    $("input[id*=attendee_name_parts_], input[id*=attendee_email]").each(function () {
        if ($(this).val()) {
            copy_to_first_ticket = false;
        }
    })
    $("input[id^=id_name_parts_], #id_email").change(function () {
        console.log(copy_to_first_ticket);
        console.log($(".questions-form").first().select("input[id*=attendee_email]"));
        console.log($("#id_email").val());
        if (copy_to_first_ticket) {
            $(".questions-form").first().find("input[id*=attendee_email]").val($("#id_email").val());
            $(".questions-form").first().find("input[id*=attendee_name_parts]").each(function () {
                var parts = $(this).attr("id").split("_");
                var num = parts[parts.length - 1];
                $(this).val($("#id_name_parts_" + num).val());
            });
        }
    });
    $("input[id*=attendee_name_parts_], input[id*=attendee_email]").change(function () {
        copy_to_first_ticket = false;
    });

    // Subevent choice
    if ($(".subevent-toggle").length) {
        $(".subevent-list").hide();
        $(".subevent-toggle").css("display", "block").click(function () {
            $(".subevent-list").slideToggle(300);
            $(".subevent-toggle").slideToggle(300)
        });
    }

    $("#monthselform select").change(function () {
        $(this).closest("form").get(0).submit();
    });

    var update_cart_form = function () {
        var is_enabled = $(".product-row input[type=checkbox]:checked, .variations input[type=checkbox]:checked, .product-row input[type=radio]:checked, .variations input[type=radio]:checked").length;
        if (!is_enabled) {
            $(".input-item-count").each(function () {
                if ($(this).val() && $(this).val() !== "0") {
                    is_enabled = true;
                }
            });
        }
        if (!is_enabled) {
            $("#btn-add-to-cart").prop("disabled", !is_enabled).popover({'content': gettext("Please enter a quantity for one of the ticket types."), 'placement': 'top', 'trigger': 'hover focus'});
        } else {
            $("#btn-add-to-cart").prop("disabled", false).popover("destroy")
        }
    };
    update_cart_form();
    $(".product-row input[type=checkbox], .variations input[type=checkbox], .product-row input[type=radio], .variations input[type=radio], .input-item-count").on("change mouseup keyup", update_cart_form);

    $(".table-calendar td.has-events").click(function () {
        var $tr = $(this).closest(".table-calendar").find(".selected-day");
        $tr.find("td").html($(this).find(".events").html());
        $tr.find("td").prepend($("<h3>").text($(this).attr("data-date")));
        $tr.show();
    });

    // Invoice address form
    $("input[data-required-if]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-required-if")),
            update = function (ev) {
                var enabled = (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val();
                if (!dependent.is("[data-no-required-attr]")) {
                    dependent.prop('required', enabled);
                }
                dependent.closest('.form-group').toggleClass('required', enabled);
            };
        update();
        dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("change", update);
        dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("dp.change", update);
    });

    $("input[data-display-dependency]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-display-dependency")),
            update = function (ev) {
                var enabled = (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val();
                if (ev) {
                    if (enabled) {
                        dependent.closest('.form-group').stop().slideDown();
                    } else {
                        dependent.closest('.form-group').stop().slideUp();
                    }
                } else {
                    dependent.closest('.form-group').toggle(enabled);
                }
            };
        update();
        dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("change", update);
        dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("dp.change", update);
    });

    form_handlers($("body"));

    // Lightbox
    lightbox.init();
});

function copy_answers(idx) {
    var elements = $('*[data-idx="' + idx + '"] input, *[data-idx="' + idx + '"] select, *[data-idx="' + idx + '"] textarea');
    var firstAnswers = $('*[data-idx="0"] input, *[data-idx="0"] select, *[data-idx="0"] textarea');
    elements.each(function (index) {
        var input = $(this),
            tagName = input.prop('tagName').toLowerCase(),
            attributeType = input.attr('type'),
            suffix = input.attr('name').split('-')[1];


        switch (tagName) {
            case "textarea":
                input.val(firstAnswers.filter("[name$=" + suffix + "]").val());
                break;
            case "select":
                input.val(firstAnswers.filter("[name$=" + suffix + "]").find(":selected").val()).change();
                break;
            case "input":
                switch (attributeType) {
                    case "text":
                    case "number":
                        input.val(firstAnswers.filter("[name$=" + suffix + "]").val());
                        break;
                    case "checkbox":
                    case "radio":
                        if (input.attr('value')) {
                            input.prop("checked", firstAnswers.filter("[name$=" + suffix + "][value=" + input.attr('value') + "]").prop("checked"));
                        } else {
                            input.prop("checked", firstAnswers.filter("[name$=" + suffix + "]").prop("checked"));
                        }
                        break;
                    default:
                        input.val(firstAnswers.filter("[name$=" + suffix + "]").val());
                }
                break;
            default:
                input.val(firstAnswers.filter("[name$=" + suffix + "]").val());
        }
    });
    questions_toggle_dependent(true);
}

