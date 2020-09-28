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

function interpolate(fmt, object, named) {
    if (named) {
        return fmt.replace(/%\(\w+\)s/g, function(match){return String(obj[match.slice(2,-2)])});
    } else {
        return fmt.replace(/%s/g, function(match){return String(obj.shift())});
    }
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

    el.find("input[data-exclusive-prefix]").each(function () {
        var $others = $("input[name^=" + $(this).attr("data-exclusive-prefix") + "]:not([name=" + $(this).attr("name") + "])");
        $(this).on('click change', function () {
            if ($(this).prop('checked')) {
                $others.prop('checked', false);
            }
        });
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
    $('input[type=radio][description]').change(function () {
        if ($(this).prop("checked")) {
            $(this).parent().parent().find('.addon-variation-description').stop().slideDown();
        }
    });

    // Copy answers
    $(".js-copy-answers").click(function (e) {
        e.preventDefault();
        e.stopPropagation();
        let idx = $(this).data('id');
        const addonDivs = $('div[data-idx="' + idx +'"]')
        addonDivs.each(function (index) {
            const elements = $(this).find('input, select, textarea');

            const addonIdx = $(this).attr("data-addonidx");
            const answersDiv = $('div[data-idx="0"][data-addonidx="' + addonIdx + '"]');
            const answers = answersDiv.find('input, select, textarea');

            copy_answers(elements, answers);
        })
        return false;
    });
    $(".js-copy-answers-addon").click(function (e) {
        e.preventDefault();
        e.stopPropagation();
        const id = $(this).data('id');
        const addonId = $(this).data('addonid');
        const addonDiv = $('div[data-idx="' + id +'"][data-addonidx="' + addonId + '"]');
        const elements = addonDiv.find('input, select, textarea');
        const answers = $('*[data-idx="' + id + '"] input, *[data-idx="' + id + '"] select, *[data-idx="' + id + '"] textarea');
        copy_answers(elements, answers);
        return false;
    });
    var copy_to_first_ticket = true;
    var attendee_address_fields = $("input[id*=attendee_name_parts_], input[id*=attendee_email], .questions-form" +
        " input[id$=company], .questions-form[id$=street], .questions-form input[id$=zipcode], .questions-form" +
        " input[id$=city]");
    attendee_address_fields.each(function () {
        if ($(this).val()) {
            copy_to_first_ticket = false;
        }
    })
    $("select[id^=id_name_parts], input[id^=id_name_parts_], #id_email, #id_street, #id_company, #id_zipcode," +
        " #id_city, #id_country, #id_state").change(function () {
        if (copy_to_first_ticket) {
            $(".questions-form").first().find("input[id*=attendee_email]").val($("#id_email").val());
            $(".questions-form").first().find("input[id$=company]").val($("#id_company").val());
            $(".questions-form").first().find("textarea[id$=street]").val($("#id_street").val());
            $(".questions-form").first().find("input[id$=zipcode]").val($("#id_zipcode").val());
            $(".questions-form").first().find("input[id$=city]").val($("#id_city").val());

            $(".questions-form").first().find("select[id$=state]").val($("#id_state").val());
            if ($(".questions-form").first().find("select[id$=country]").val() !== $("#id_country").val()) {
                $(".questions-form").first().find("select[id$=country]").val($("#id_country").val()).trigger('change');
            }
            $(".questions-form").first().find("[id*=attendee_name_parts]").each(function () {
                var parts = $(this).attr("id").split("_");
                var num = parts[parts.length - 1];
                $(this).val($("#id_name_parts_" + num).val());
            });
        }
    });
    attendee_address_fields.change(function () {
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
            $(".input-seat-selection option").each(function() {
                if ($(this).val() && $(this).val() !== "" && $(this).prop('selected')) {
                    is_enabled = true;
                }
            });
        }
        if (!is_enabled && !$(".has-seating").length) {
            $("#btn-add-to-cart").prop("disabled", !is_enabled).popover({
                'content': function () { return gettext("Please enter a quantity for one of the ticket types.") },
                'placement': 'top',
                'trigger': 'hover focus'
            });
        } else {
            $("#btn-add-to-cart").prop("disabled", false).popover("destroy")
        }
    };
    update_cart_form();
    $(".product-row input[type=checkbox], .variations input[type=checkbox], .product-row input[type=radio], .variations input[type=radio], .input-item-count, .input-seat-selection")
        .on("change mouseup keyup", update_cart_form);

    $(".table-calendar td.has-events").click(function () {
        var $tr = $(this).closest(".table-calendar").find(".selected-day");
        $tr.find("td").html($(this).find(".events").html());
        $tr.find("td").prepend($("<h3>").text($(this).attr("data-date")));
        $tr.show();
    });

    $(".print-this-page").on("click", function (e) {
        window.print();
        e.preventDefault();
        return true;
    });

    $("input[data-required-if], select[data-required-if], textarea[data-required-if]").each(function () {
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

    $("input[data-display-dependency], div[data-display-dependency], select[data-display-dependency], textarea[data-display-dependency]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-display-dependency")),
            update = function (ev) {
                var enabled = (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val();
                var $toggling = dependent;
                if (dependent.get(0).tagName.toLowerCase() !== "div") {
                    $toggling = dependent.closest('.form-group');
                }
                if (ev) {
                    if (enabled) {
                        $toggling.stop().slideDown();
                    } else {
                        $toggling.stop().slideUp();
                    }
                } else {
                    $toggling.stop().toggle(enabled);
                }
            };
        update();
        dependency.closest('.form-group, form').find('input[name=' + dependency.attr("name") + ']').on("change", update);
        dependency.closest('.form-group, form').find('input[name=' + dependency.attr("name") + ']').on("dp.change", update);
    });

    $("input[name$=vat_id][data-countries-in-eu]").each(function () {
        var dependent = $(this),
            dependency_country = $(this).closest(".panel-body, form").find('select[name$=country]'),
            dependency_id_is_business_1 = $(this).closest(".panel-body, form").find('input[id$=id_is_business_1]'),
            update = function (ev) {
                if (dependency_id_is_business_1.length && !dependency_id_is_business_1.prop("checked")) {
                    dependent.closest(".form-group").hide();
                } else if (dependent.attr('data-countries-in-eu').split(',').includes(dependency_country.val())) {
                    dependent.closest(".form-group").show();
                } else {
                    dependent.closest(".form-group").hide();
                }
            };
        update();
        dependency_country.on("change", update);
        dependency_id_is_business_1.on("change", update);
    });

    $("select[name$=state]").each(function () {
        var dependent = $(this),
            counter = 0,
            dependency = $(this).closest(".panel-body, form").find('select[name$=country]'),
            update = function (ev) {
                counter++;
                var curCounter = counter;
                dependent.prop("disabled", true);
                dependency.closest(".form-group").find("label").prepend("<span class='fa fa-cog fa-spin'></span> ");
                $.getJSON('/js_helpers/states/?country=' + dependency.val(), function (data) {
                    if (counter > curCounter) {
                        return;  // Lost race
                    }
                    dependent.find("option").filter(function (t) {return !!$(this).attr("value")}).remove();
                    if (data.data.length > 0) {
                        $.each(data.data, function (k, s) {
                            dependent.append($("<option>").attr("value", s.code).text(s.name));
                        });
                        dependent.closest(".form-group").show();
                        dependent.prop('required', dependency.prop("required"));
                    } else {
                        dependent.closest(".form-group").hide();
                        dependent.prop("required", false);
                    }
                    dependent.prop("disabled", false);
                    dependency.closest(".form-group").find("label .fa-spin").remove();
                });
            };
        if (dependent.find("option").length === 1) {
            dependent.closest(".form-group").hide();
        } else {
            dependent.prop('required', dependency.prop("required"));
        }
        dependency.on("change", update);
    });

    form_handlers($("body"));

    var cancel_fee_slider_update = function () {
        if (typeof django === "undefined") {
            window.setTimeout(cancel_fee_slider_update, 100);
            return;
        }
        $("#cancel-fee-keep").text(interpolate(
            gettext("The organizer keeps %(currency)s %(amount)s"),
            {
                'currency': $("body").attr("data-currency"),
                'amount': floatformat(cancel_fee_slider.getValue(), 2)
            },
            true
        ));
        $("#cancel-fee-refund").text(interpolate(
            gettext("You get %(currency)s %(amount)s back"),
            {
                'currency': $("body").attr("data-currency"),
                'amount': floatformat((cancel_fee_slider.getAttribute("max") - cancel_fee_slider.getValue()), 2)
            },
            true
        ));
    }
    var cancel_fee_slider = $('#cancel-fee-slider').slider({
    }).on('slide', function () {
        cancel_fee_slider_update();
    }).data('slider');
    if (cancel_fee_slider) {
        cancel_fee_slider_update();
        $("#cancel-fee-custom").click(function () {
            try {
                var newinp = parseFloat(prompt(gettext("Please enter the amount the organizer can keep."), cancel_fee_slider.getValue().toString()).replace(',', '.'));
                cancel_fee_slider.setValue(newinp);
                cancel_fee_slider_update();
            } catch (e) {
            }
        });
    }

    var local_tz = moment.tz.guess()
    $("span[data-timezone]").each(function() {
        var t = moment.tz($(this).attr("data-time"), $(this).attr("data-timezone"))
        var tz = moment.tz.zone($(this).attr("data-timezone"))

        $(this).tooltip({
            'title': gettext("Time zone:") + " " + tz.abbr(t)
        });
        if (t.tz(tz.name).format() !== t.tz(local_tz).format()) {
            var $add = $("<span>").addClass("text-muted")
            $add.append($("<span>").addClass("fa fa-globe"))
            $add.append(" " + gettext("Your local time:") + " ")
            if (t.tz(tz.name).format("YYYY-MM-DD") != t.tz(local_tz).format("YYYY-MM-DD")) {
                $add.append(t.tz(local_tz).format($("body").attr("data-datetimeformat")))
            } else {
                $add.append(t.tz(local_tz).format($("body").attr("data-timeformat")))
            }
            $add.insertAfter($(this));
            $add.tooltip({
                'title': gettext("Time zone:") + " " + moment.tz.zone(local_tz).abbr(t)
            });
        }
    });

    // Lightbox
    lightbox.init();
});

function copy_answers(elements, answers) {
   elements.each(function (index) {
        var input = $(this),
            tagName = input.prop('tagName').toLowerCase(),
            attributeType = input.attr('type'),
            suffix = input.attr('name').split('-')[1];

        switch (tagName) {
            case "textarea":
                input.val(answers.filter("[name$=" + suffix + "]").val());
                break;
            case "select":
                input.val(answers.filter("[name$=" + suffix + "]").find(":selected").val()).change();
                break;
            case "input":
                switch (attributeType) {
                    case "text":
                    case "number":
                        input.val(answers.filter("[name$=" + suffix + "]").val());
                        break;
                    case "checkbox":
                    case "radio":
                        if (input.attr('value')) {
                            input.prop("checked", answers.filter("[name$=" + suffix + "][value=" + input.attr('value') + "]").prop("checked"));
                        } else {
                            input.prop("checked", answers.filter("[name$=" + suffix + "]").prop("checked"));
                        }
                        break;
                    default:
                        input.val(answers.filter("[name$=" + suffix + "]").val());
                }
                break;
            default:
                input.val(answers.filter("[name$=" + suffix + "]").val());
        }
    });
    questions_toggle_dependent(true);
}