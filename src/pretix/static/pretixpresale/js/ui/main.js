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
    el.find('input, select, textarea').on('invalid', function (e) {
        if (!$(this).is(':visible')) {
            var panel = $(this).closest('.panel');
            if (!panel.attr('open')) panel.addClass('details-open').attr('open', true).children(':not(summary)').slideDown();
            if (!$(document.activeElement).is(':invalid')) this.focus();
        }
    });

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
                previous: $("html").hasClass("rtl") ? 'fa fa-chevron-right' : 'fa fa-chevron-left',
                next: $("html").hasClass("rtl") ? 'fa fa-chevron-left' : 'fa fa-chevron-right',
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
                previous: $("html").hasClass("rtl") ? 'fa fa-chevron-right' : 'fa fa-chevron-left',
                next: $("html").hasClass("rtl") ? 'fa fa-chevron-left' : 'fa fa-chevron-right',
                today: 'fa fa-screenshot',
                clear: 'fa fa-trash',
                close: 'fa fa-remove'
            },
        };
        if ($(this).is('[data-min]')) {
            opts["minDate"] = $(this).attr("data-min");
            opts["viewDate"] = $(this).attr("data-min");
        }
        if ($(this).is('[data-max]')) {
            opts["maxDate"] = $(this).attr("data-max");
            opts["viewDate"] = $(this).attr("data-max");
        }
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
                previous: $("html").hasClass("rtl") ? 'fa fa-chevron-right' : 'fa fa-chevron-left',
                next: $("html").hasClass("rtl") ? 'fa fa-chevron-left' : 'fa fa-chevron-right',
                today: 'fa fa-screenshot',
                clear: 'fa fa-trash',
                close: 'fa fa-remove'
            }
        };
        $(this).datetimepicker(opts);
    });

    el.find(".input-item-count-dec, .input-item-count-inc").on("click", function (e) {
        e.preventDefault();
        var step = parseFloat(this.getAttribute("data-step"));
        var controls = document.getElementById(this.getAttribute("data-controls"));
        var currentValue = parseFloat(controls.value);
        controls.value = Math.max(controls.min, Math.min(controls.max || Number.MAX_SAFE_INTEGER, (currentValue || 0) + step));
        controls.dispatchEvent(new Event("change"));
    });
    el.find(".btn-checkbox input").on("change", function (e) {
        $(this).closest(".btn-checkbox")
            .toggleClass("btn-checkbox-checked", this.checked)
            .find(".fa").toggleClass("fa-shopping-cart", !this.checked).toggleClass("fa-cart-arrow-down", this.checked);
    });
    el.find(".btn-checkbox:has([checked])")
        .addClass("btn-checkbox-checked")
        .find(".fa-shopping-cart")
        .removeClass("fa-shopping-cart")
        .addClass("fa-cart-arrow-down");

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
        ).find("canvas").attr("role", "img").attr("aria-label", this.getAttribute("data-desc"));
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
    questions_init_photos(el);

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
    var cancel_fee_slider = el.find('#cancel-fee-slider').slider({
    }).on('slide', function () {
        cancel_fee_slider_update();
    }).data('slider');
    if (cancel_fee_slider) {
        cancel_fee_slider_update();
        el.find("#cancel-fee-custom").click(function () {
            try {
                var newinp = parseFloat(prompt(gettext("Please enter the amount the organizer can keep."), cancel_fee_slider.getValue().toString()).replace(',', '.'));
                cancel_fee_slider.setValue(newinp);
                cancel_fee_slider_update();
            } catch (e) {
            }
        });
    }
};

function setup_basics(el) {
    el.find("input[data-toggle=radiocollapse]").change(function () {
        $($(this).attr("data-parent")).find(".collapse.in").collapse('hide');
        $($(this).attr("data-target")).collapse('show');
    });
    el.find("input[data-toggle=radiocollapse]:checked").each(function () {
        if (!$($(this).attr("data-parent")).find(".collapse.in").length) {
            $($(this).attr("data-target")).collapse('show');
        }
    });
    el.find(".js-only").removeClass("js-only");
    el.find(".js-hidden").hide();

    el.find("div.collapsed").removeClass("collapsed").addClass("collapse");
    el.find(".has-error, .alert-danger").each(function () {
        $(this).closest("div.panel-collapse").collapse("show");
    });
    el.find(".has-error").first().each(function(){
        if ($(this).is(':input')) this.focus();
        else $(":input", this).get(0).focus();
    });
    el.find(".alert-danger").first().each(function() {
        var container = this;
        var content = $("<ul></ul>").click(function(e) {
            var input = $(e.target.hash).get(0);
            if (input) input.focus();
            input.scrollIntoView({block: "center"});
            e.preventDefault();
        });
        $(".has-error").each(function() {
            var target = target = $(":input", this);
            var desc = target && target.attr("aria-describedby") ? document.getElementById(target.attr("aria-describedby").split(' ', 1)[0]) : null;
            if (!target || !desc || desc == container) return;

            // multi-input fields have a role=group with aria-labelledby
            var label = this.hasAttribute("aria-labelledby") ? $("#" + this.getAttribute("aria-labelledby")) : $("[for="+target.attr("id")+"]");

            var $li = $("<li>");
            $li.text(": " + desc.textContent)
            $li.prepend($("<a>").attr("href", "#" + target.attr("id")).text(label.get(0).childNodes[0].nodeValue))
            content.append($li);
        });
        $(this).append(content);
    });

    el.find("[data-click-to-load]").on("click", function(e) {
        var target = document.getElementById(this.getAttribute("data-click-to-load"));
        target.src = this.href;
        target.focus();
        e.preventDefault();
    });

    el.find('[data-toggle="tooltip"]').tooltip();

    // AddOns
    el.find('.addon-variation-description').hide();
    el.find('.toggle-variation-description').click(function () {
        $(this).parent().find('.addon-variation-description').slideToggle();
    });
    el.find('input[type=radio][description]').change(function () {
        if ($(this).prop("checked")) {
            $(this).parent().parent().find('.addon-variation-description').stop().slideDown();
        }
    });
}

function setup_week_calendar() {
    // Week calendar
    // On mobile, auto-collapse all days except today, if we have more than 15 events in total
    if ($(window).width() < 992 && $(".week-calendar .event").length > 15) {
        $(".week-calendar .weekday:not(.today)").each(function () {
            $(this).prop("open", false);
        });
    }
}

$(function () {
    "use strict";

    $("body").removeClass("nojs");

    var scrollpos = sessionStorage ? sessionStorage.getItem('scrollpos') : 0;
    if (scrollpos) {
        window.scrollTo(0, scrollpos);
        sessionStorage.removeItem('scrollpos');
    }

    $(".accordion-radio").click(function() {
        var $input = $("input", this);
        if (!$input.prop("checked")) $input.prop('checked', true).trigger("change");
    });

    setup_basics($("body"));
    $(".overlay-remove").on("click", function() {
        $(this).closest(".contains-overlay").find(".overlay").fadeOut();
    });

    $("#voucher-box").hide();
    $("#voucher-toggle").show();
    $("#voucher-toggle a").click(function () {
        $("#voucher-box").slideDown();
        $("#voucher-toggle").slideUp();
    });

    $("#ajaxerr").on("click", ".ajaxerr-close", ajaxErrDialog.hide);

    // Copy answers
    $(".js-copy-answers").click(function (e) {
        e.preventDefault();
        e.stopPropagation();
        var idx = $(this).data('id');
        var addonDivs = $('div[data-idx="' + idx +'"]');
        addonDivs.each(function (index) {
            var elements = $(this).find('input, select, textarea');

            var addonIdx = $(this).attr("data-addonidx");
            var answersDiv = $('div[data-idx="' + (idx - 1) + '"][data-addonidx="' + addonIdx + '"]');
            var answers = answersDiv.find('input, select, textarea');

            copy_answers(elements, answers);
        })
        return false;
    });
    $(".js-copy-answers-addon").click(function (e) {
        e.preventDefault();
        e.stopPropagation();
        var id = $(this).data('id');
        var addonId = $(this).data('addonid');
        var addonDiv = $('div[data-idx="' + id +'"][data-addonidx="' + addonId + '"]');
        var elements = addonDiv.find('input, select, textarea');
        var answers = $('[data-idx="' + id + '"][data-addonidx="' + (addonId - 1) + '"] input, [data-idx="' + id + '"][data-addonidx="' + (addonId - 1) + '"] select, [data-idx="' + id + '"][data-addonidx="' + (addonId - 1) + '"] textarea').reverse();
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
            var $first_ticket_form = $(".questions-form").first().find("[data-addonidx=0]");
            $first_ticket_form.find("input[id*=attendee_email]").val($("#id_email").val());
            $first_ticket_form.find("input[id$=company]").val($("#id_company").val());
            $first_ticket_form.find("textarea[id$=street]").val($("#id_street").val());
            $first_ticket_form.find("input[id$=zipcode]").val($("#id_zipcode").val());
            $first_ticket_form.find("input[id$=city]").val($("#id_city").val());

            $first_ticket_form.find("select[id$=state]").val($("#id_state").val());
            if ($first_ticket_form.find("select[id$=country]").val() !== $("#id_country").val()) {
                $first_ticket_form.find("select[id$=country]").val($("#id_country").val()).trigger('change');
            }
            $first_ticket_form.find("[id*=attendee_name_parts]").each(function () {
                var parts = $(this).attr("id").split("_");
                var num = parts[parts.length - 1];
                $(this).val($("#id_name_parts_" + num).val());
            });
        }
    });
    attendee_address_fields.change(function () {
        copy_to_first_ticket = false;
    });
    questions_init_profiles($("body"));

    // Subevent choice
    if ($(".subevent-toggle").length) {
        $(".subevent-list").hide();
        $(".subevent-toggle").show().click(function () {
            $(".subevent-list").slideToggle(300);
            $(this).slideToggle(300).attr("aria-expanded", true);
        });
    }
    if (sessionStorage) {
        $("[data-save-scrollpos]").click(function () {
            sessionStorage.setItem('scrollpos', window.scrollY);
        });
    }
    $("#monthselform select").change(function () {
        if (sessionStorage) sessionStorage.setItem('scrollpos', window.scrollY);
        this.form.submit();
    });
    $("#monthselform input").on("dp.change", function () {
        if ($(this).data("DateTimePicker")) {  // prevent submit after dp init
            if (sessionStorage) sessionStorage.setItem('scrollpos', window.scrollY);
            this.form.submit();
        }
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
        if (!is_enabled && (!$(".has-seating").length || $("#seating-dummy-item-count").length)) {
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
        $tr.find("td").html($(this).find(".events").clone());
        $tr.find("td").prepend($("<h3>").text($(this).attr("data-date")));
        $tr.removeClass("hidden");
    });

    $(".print-this-page").on("click", function (e) {
        window.print();
        e.preventDefault();
        return true;
    });

    $("input[data-required-if], select[data-required-if], textarea[data-required-if]").each(function () {
        var dependent = $(this),
            dependentLabel = $("label[for="+this.id+"]"),
            dependency = $($(this).attr("data-required-if")),
            update = function (ev) {
                var enabled = (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val();
                if (!dependent.is("[data-no-required-attr]")) {
                    dependent.prop('required', enabled);
                }
                dependent.closest('.form-group').toggleClass('required', enabled);
                if (enabled) {
                    dependentLabel.append('<i class="sr-only label-required">, ' + gettext('required') + '</i>');
                }
                else {
                    dependentLabel.find(".label-required").remove();
                }
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
        dependency.closest('.form-group, form').find('input[name=' + dependency.attr("name") + '], select[name=' + dependency.attr("name") + ']').on("change", update);
        dependency.closest('.form-group, form').find('input[name=' + dependency.attr("name") + ']').on("dp.change", update);
    });

    $("input[name$=vat_id][data-countries-with-vat-id]").each(function () {
        var dependent = $(this),
            dependency_country = $(this).closest(".panel-body, form").find('select[name$=country]'),
            dependency_id_is_business_1 = $(this).closest(".panel-body, form").find('input[id$=id_is_business_1]'),
            update = function (ev) {
                if (dependency_id_is_business_1.length && !dependency_id_is_business_1.prop("checked")) {
                    dependent.closest(".form-group").hide();
                } else if (dependent.attr('data-countries-with-vat-id').split(',').includes(dependency_country.val())) {
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
                    var selected_value = dependent.prop("data-selected-value");
                    dependent.find("option").filter(function (t) {return !!$(this).attr("value")}).remove();
                    if (data.data.length > 0) {
                        $.each(data.data, function (k, s) {
                            var o = $("<option>").attr("value", s.code).text(s.name);
                            if (s.code == selected_value || (selected_value && selected_value.indexOf && selected_value.indexOf(s.code) > -1)) {
                                o.prop("selected", true);
                            }
                            dependent.append(o);
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

    var local_tz = moment.tz.guess()
    $("span[data-timezone], small[data-timezone]").each(function() {
        var t = moment.tz($(this).attr("data-time"), $(this).attr("data-timezone"))
        var tz = moment.tz.zone($(this).attr("data-timezone"))
        var tpl = '<div class="tooltip" role="tooltip"><div class="tooltip-arrow"></div><div class="tooltip-inner text-nowrap"></div></div>';

        $(this).tooltip({
            "title": gettext("Time zone:") + " " + tz.abbr(t),
            "template": tpl
        });
        if (t.tz(tz.name).format() !== t.tz(local_tz).format()) {
            var $add = $("<span>")
            $add.append($("<span>").addClass("fa fa-globe"))
            if ($(this).is("[data-time-short]")) {
                $add.append($("<em>").text(" " + t.tz(local_tz).format($("body").attr("data-timeformat"))))
            } else {
                $add.addClass("text-muted")
                $add.append(" " + gettext("Your local time:") + " ")
                if (t.tz(tz.name).format("YYYY-MM-DD") != t.tz(local_tz).format("YYYY-MM-DD")) {
                    $add.append(t.tz(local_tz).format($("body").attr("data-datetimeformat")))
                } else {
                    $add.append(t.tz(local_tz).format($("body").attr("data-timeformat")))
                }
            }
            $add.insertAfter($(this));
            $add.tooltip({
                "title": gettext("Time zone:") + " " + moment.tz.zone(local_tz).abbr(t),
                "template": tpl
            });
        }
    });

    // For a very weird reason, window width is 0 on an initial load of the widget
    if ($(window).width() > 0) {
        setup_week_calendar()
    } else {
        $(window).on('resize', setup_week_calendar)
    }

    // Day calendar
    $(".day-calendar [data-concurrency]").each(function() {
        var c = parseInt(this.getAttribute("data-concurrency"), 10);
        if (c > 9) this.style.setProperty('--concurrency', c);
    });

    $(".day-calendar").each(function() {
        // Fix Chrome not being able to use calc-division in grid
        var s = window.getComputedStyle($(".day-timeline > li").get(0));
        if (s.getPropertyValue('grid-column-start') != "auto") return;

        var rasterSize = this.getAttribute("data-raster-size");
        var duration = this.getAttribute("data-duration").split(":");
        var cols = duration[0]*60/rasterSize + duration[1]/rasterSize;

        $(".day-timeline", this).css("grid-template-columns", "repeat(" + cols + ", minmax(var(--col-min-size, 3em), 1fr))");

        $(".day-timeline > li", this).each(function() {
            var s = window.getComputedStyle(this);

            var offset = this.getAttribute("data-offset").split(":");
            var duration = this.getAttribute("data-duration").split(":");

            var columnStart = 1 + offset[0]*60/rasterSize + offset[1]/rasterSize;
            var columnSpan = duration[0]*60/rasterSize + duration[1]/rasterSize
            this.style.gridColumn = columnStart + " / span " + columnSpan;
        });
    });

    $(".day-calendar").each(function() {

        var timezone = this.getAttribute("data-timezone");
        var startTime = moment.tz(this.getAttribute("data-start"), timezone);

        var currentTime = moment().tz(timezone);
        if (!currentTime.isSame(startTime, 'day')) {
            // Not on same day
            return;
        }

        // scroll to best matching tick
        var currentTimeCmp = parseInt(currentTime.format("Hmm"), 10);
        var ticks = this.querySelectorAll(".ticks li");
        var currentTick;
        var t;
        for (var i=0, max=ticks.length; i < max; i++) {
            currentTick = ticks[i]
            t = parseInt(currentTick.getAttribute("data-start").replace(":", ""), 10);
            if (t > currentTimeCmp) {
                currentTick = ticks[Math.max(i-1, 0)]
                break;
            }
        }
        if (currentTick.offsetLeft > 0.66*this.offsetWidth) {
            this.scrollLeft = Math.max(currentTick.offsetLeft - this.offsetWidth/2, 0);
        }


        var thisCalendar = this;
        var currentTimeInterval;

        var timeFormat = document.body.getAttribute("data-timeformat");
        var timeFormatParts = timeFormat.match(/([a-zA-Z_\s]+)([^a-zA-Z_\s])(.*)/);
        if (!timeFormatParts) timeFormatParts = [timeFormat];
        if (timeFormatParts.length > 1) timeFormatParts.shift();
        var currentTimeBar = $('<div class="current-time-bar" aria-hidden="true"><time></time></div>').appendTo(this);
        var currentTimeDisplay = currentTimeBar.find("time");
        var currentTimeDisplayParts = [];
        timeFormatParts.forEach(function(format) {
            currentTimeDisplayParts.push([format, $("<span></span>").appendTo(currentTimeDisplay)])
        }); 
        var duration = this.getAttribute("data-duration").split(":").reduce(function(previousValue, currentValue, currentIndex) {
            return previousValue + (currentIndex ? parseInt(currentValue, 10) * 60 : parseInt(currentValue, 10) * 60 * 60);
        }, 0);
        function setCurrentTimeBar() {
            var currentTime = moment().tz(timezone);
            var currentTimeDelta = Math.floor((currentTime - startTime)/1000);
            if (currentTimeDelta < 0 || currentTimeDelta > duration) {
                // Too early || Too late
                window.clearInterval(currentTimeInterval);
                currentTimeBar.remove();
                return;
            }
            
            var offset = thisCalendar.querySelector("h3").getBoundingClientRect().width;
            var dx = Math.round(offset + (thisCalendar.scrollWidth-offset)*(currentTimeDelta/duration));
            currentTimeDisplayParts.forEach(function(part) {
                part[1].text(currentTime.format(part[0]));
            });
            if (currentTimeDisplay.get(0).getBoundingClientRect().width + dx >= thisCalendar.scrollWidth) {
                currentTimeBar.addClass("swap-side");
            }
            else {
                currentTimeBar.removeClass("swap-side");
            }
            thisCalendar.style.setProperty('--current-time-offset', dx + "px");
        }
        currentTimeInterval = window.setInterval(setCurrentTimeBar, 15*1000);
        $(window).on("resize", setCurrentTimeBar);
        setCurrentTimeBar();
    });

    // Lightbox
    lightbox.init();

    // free-range price input auto-check checkbox/set count-input to 1 if 0
    $("[data-checked-onchange]").each(function() {
        var countInput = this;
        $("#" + this.getAttribute("data-checked-onchange")).on("change", function() {
            if (countInput.type === "checkbox") {
                if (countInput.checked) return;
                countInput.checked = true;
            }
            else if (countInput.type === "number" && !countInput.valueAsNumber) {
                countInput.value = "1";
            }
            else {
                return;
            }
            // in case of a change, trigger event
            $(countInput).trigger("change");
        });
    });
});

function copy_answers(elements, answers) {
   elements.not("[disabled], [readonly]").each(function (index) {
        if (!this.name) return;
        var input = $(this),
            tagName = input.prop('tagName').toLowerCase(),
            attributeType = input.attr('type'),
            suffix = input.attr('name').split('-')[1];
        if (input.closest(".js-do-not-copy-answers").length) return;

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
                    case "file":
                        break
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
