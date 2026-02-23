/*global $, gettext, ngettext, interpolate */

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
            keepInvalid: true,
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
            opts["viewDate"] = (opts.minDate &&   // if minDate and maxDate are set, use the one closer to now as viewDate
                    Math.abs(+new Date(opts.minDate) - new Date()) < Math.abs(+new Date(opts.maxDate) - new Date())
            ) ? opts.minDate : opts.maxDate;
        }
        $(this).datetimepicker(opts).on("dp.hide", function() {
            // when min/max is used in datetimepicker, closing and re-opening the picker opens at the wrong date
            // therefore keep the current viewDate and re-set it after datetimepicker is done hiding
            var $dtp = $(this).data("DateTimePicker");
            var currentViewDate = $dtp.viewDate();
            window.setTimeout(function () {
                $dtp.viewDate(currentViewDate);
            }, 50);
        });
        if ($(this).parent().is('.splitdatetimerow')) {
            $(this).on("dp.change", function (ev) {
                var $timepicker = $(this).closest(".splitdatetimerow").find(".timepickerfield");
                var date = $(this).data('DateTimePicker').date();
                if (date === null) {
                    return;
                }
                if ($timepicker.val() === "") {
                    if (/_(until|end|to)(_|$)/.test($(this).attr("name"))) {
                        date.set({'hour': 23, 'minute': 59, 'second': 59});
                    } else {
                        date.set({'hour': 0, 'minute': 0, 'second': 0});
                    }
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
        controls.dispatchEvent(new Event("change", { bubbles: true }));
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


    el.find("fieldset[data-addon-max-count]").each(function() {
        // usually addons are only allowed once one per item
        var multipleAllowed = this.hasAttribute("data-addon-multi-allowed");
        var $inputs = $(".availability-box input", this);
        var max = parseInt(this.getAttribute("data-addon-max-count"));
        var desc = $(".addon-count-desc", this).text().trim();
        this.addEventListener("change", function (e) {
            var variations = e.target.closest(".variations");
            if (variations && !multipleAllowed && e.target.checked) {
                // uncheck all other checkboxes inside this variations
                $(".availability-box input:checked", variations).not(e.target).prop("checked", false).trigger("change");
            }

            if (max === 1) {
                if (e.target.checked) {
                    $inputs.filter(":checked").not(e.target).prop("checked", false).trigger("change");
                }
                return;
            }
            var total = $inputs.toArray().reduce(function(a, e) {
                return a + (e.type == "checkbox" ? (e.checked ? parseInt(e.value) : 0) : parseInt(e.value) || 0);
            }, 0);
            if (total > max) {
                if (e.target.type == "checkbox") {
                    e.target.checked = false;
                } else {
                    e.target.value = e.target.value - (total - max);
                }
                $(e.target).trigger("change").closest(".availability-box").tooltip({
                    "title": desc,
                }).tooltip('show');
                e.preventDefault();
            } else {
                $(".availability-box", this).tooltip('destroy')
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

    el.find('.use_giftcard').on("click", function () {
        var value = $(this).data('value');
        $('#id_payment_giftcard-code').val(value)
    })

};

function setup_basics(el) {
    el.find("form").attr("novalidate", true).on("submit", function (e) {
        if (!this.checkValidity()) {
            var input = this.querySelector(":invalid:not(fieldset)");
            (input.labels[0] || input).scrollIntoView();
            // only use reportValidity, which usually sets focus on element
            // input.focus() opens dropdowns, which is not what we want
            input.reportValidity();
            e.preventDefault();
        }
    });
    el.find("input[data-toggle=radiocollapse]").change(function () {
        $($(this).attr("data-parent")).find(".collapse.in").collapse('hide');
        $($(this).attr("data-target")).collapse('show');
    });
    el.find("input[data-toggle=radiocollapse]:checked").each(function () {
        if (!$($(this).attr("data-parent")).find(".collapse.in").length) {
            $($(this).attr("data-target")).collapse('show');
        }
    });
    $("fieldset.accordion-panel > legend input[type=radio]").change(function() {
        $(this).closest("fieldset").siblings("fieldset").prop('disabled', true).children('.panel-body').slideUp();
        $(this).closest("fieldset").prop('disabled', false).children('.panel-body').slideDown();
    }).filter(':not(:checked)').each(function() { $(this).closest("fieldset").prop('disabled', true).children('.panel-body').hide(); });

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

    // tabs - see https://www.w3.org/WAI/ARIA/apg/patterns/tabs/examples/tabs-automatic/ for reference
    el.find('.tabcontainer').each(function() {
        var currentTab;
        function setCurrentTab(tab) {
            if (tab == currentTab) return;
            if (currentTab) {
                currentTab.setAttribute('aria-selected', 'false');
                currentTab.tabIndex = -1;
                currentTab.classList.remove('active');
                document.getElementById(currentTab.getAttribute('aria-controls')).setAttribute('hidden', 'hidden');
            }
            tab.setAttribute('aria-selected', 'true');
            tab.removeAttribute('tabindex');
            tab.classList.add('active');
            document.getElementById(tab.getAttribute('aria-controls')).removeAttribute('hidden');
            currentTab = tab;
        }
        var tabs = $('button[role=tab]').on('keydown', function(event) {
            if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].indexOf(event.key) == -1) {
                return;
            }
            event.stopPropagation();
            event.preventDefault();

            if (event.key == 'ArrowLeft') {
                setCurrentTab(currentTab.previousElementSibling || lastTab);
            } else if (event.key == 'ArrowRight') {
                setCurrentTab(currentTab.nextElementSibling || firstTab);
            } else if (event.key == 'Home') {
                setCurrentTab(firstTab);
            } else if (event.key == 'End') {
                setCurrentTab(lastTab);
            }
            currentTab.focus();
        }).on('click', function (event) {
            setCurrentTab(this);
        });
        
        var firstTab = tabs.first().get(0);
        var lastTab = tabs.last().get(0);
        setCurrentTab(tabs.filter('[aria-selected=true]').get(0));
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

function get_label_text_for_id(id) {
    return $("label[for=" + id +"]").first().contents().filter(function () {
        return this.nodeType != Node.ELEMENT_NODE || !this.classList.contains("sr-only");
    }).text().trim();
}

$(function () {
    "use strict";

    $("body").removeClass("nojs");
    moment.locale($("body").attr("data-datetimelocale"));

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

    // Handlers for "Copy answers from above" buttons
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

    // Automatically copy answers from invoice to first attendee
    var attendee_address_fields = $("input[id*=attendee_name_parts_], input[id*=attendee_email], " +
        ".questions-form input[id$=company], .questions-form input[id$=street], " +
        ".questions-form input[id$=zipcode], .questions-form input[id$=city]");
    function copy_to_first_ticket () {
        var source = this;
        var source_label = get_label_text_for_id(source.id);

        var $first_ticket_form = $(".questions-form").first().find("[data-addonidx=0]");
        var $candidates = $first_ticket_form.find(source.tagName + ":not([type='checkbox'], [type='radio'], [type='hidden'])");
        var $match = $candidates.filter(function() {
            return (
                this.id.endsWith(source.id.substring(3))
                || (this.placeholder && this.placeholder === source.placeholder)
                || (this.placeholder && this.placeholder === source_label)
                || (source_label && this.id && get_label_text_for_id(this.id) === source_label)
            );
        }).first();
        $match.val(this.value).trigger("change");
    }
    function valueIsEmpty(el) { return !el.value; }
    if (attendee_address_fields.toArray().every(valueIsEmpty)) {
        var invoice_address_fields = $("select[id^=id_name_parts], input[id^=id_name_parts_], #id_email, #id_street, " +
            "#id_company, #id_zipcode, #id_city, #id_country, #id_state");
        invoice_address_fields.on("change", copy_to_first_ticket).trigger("change");
        attendee_address_fields.one("input", function () {
            invoice_address_fields.off("change", copy_to_first_ticket);
        });
    }

    questions_init_profiles($("body"));

    if (sessionStorage) {
        $("[data-save-scrollpos]").on("click submit", function () {
            sessionStorage.setItem('scrollpos', window.scrollY);
        });
        $("#monthselform").on("submit", function () {
            sessionStorage.setItem('scrollpos', window.scrollY);
        });
    }
    $("form:has(#btn-add-to-cart)").on("submit", function(e) {
        if (
            this.querySelector("pretix-seating-checkout-button button") ||
            this.querySelector("input[type=checkbox]:checked, input[type=radio]:checked") ||
            [...this.querySelectorAll(".input-item-count:not([type=hidden])")].some(input => input.value && input.value !== "0") // TODO: seating adds a hidden seating-dummy-item-count, which is not useful and should at some point be removed
        ) {
            // okay, let the submit-event bubble to async-task
            return;
        }

        e.preventDefault();
        e.stopPropagation();

        document.querySelector("#dialog-nothing-to-add").showModal();
    });

    $(".table-calendar td.has-events").click(function () {
        var $grid = $(this).closest("[role='grid']");
        $grid.find("[aria-selected]").attr("aria-selected", false);
        $(this).attr("aria-selected", true);
        $("#selected-day")
            .html($(this).find(".events").clone())
            .prepend($("<h3>").text($(this).attr("data-date")));
    }).each(function() {
        // check all events classes and set the "winning" class for the availability of the day-label on mobile
        var $dayLabel = $('.day-label', this);
        if ($('.available.low', this).length == $('.available', this).length) {
            $dayLabel.addClass('low');
        }
        var classes = ['available', 'waitinglist', 'soon', 'reserved', 'soldout', 'continued', 'over'];
        for (var c of classes) {
            if ($('.'+c, this).length) {
                $dayLabel.addClass(c);
                // CAREFUL: „return“ as „break“ is not supported before ES2015 and breaks e.g. on iOS 15
                return;
            }
        }
    });

    $(".print-this-page").on("click", function (e) {
        window.print();
        e.preventDefault();
        return true;
    });

    $("input[data-required-if], select[data-required-if], textarea[data-required-if]").each(function () {
        var dependent = $(this),
            dependentLabel = $("label[for="+this.id+"]"),
            dependencies = $($(this).attr("data-required-if")),
            update = function (ev) {
                var enabled = true;
                dependencies.each(function () {
                    var dependency = $(this);
                    var e = (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val();
                    enabled = enabled && e;
                });
                if (!dependent.is("[data-no-required-attr]")) {
                    dependent.prop('required', enabled);
                }
                if (enabled) {
                    dependentLabel.append('<i class="label-required">' + gettext('required') + '</i>');
                }
                else {
                    dependentLabel.find(".label-required").remove();
                }
            };
        update();
        dependencies.each(function () {
            var dependency = $(this);
            dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("change", update);
            dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("dp.change", update);
        });
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

    form_handlers($("body"));

    var local_tz = moment.tz.guess()
    $(".event-is-remote span[data-timezone]").each(function() {
        var t = moment.tz($(this).attr("datetime") || $(this).attr("data-time"), $(this).attr("data-timezone"))
        var tz = moment.tz.zone($(this).attr("data-timezone"))

        if (t.tz(tz.name).format() !== t.tz(local_tz).format()) {
            var format = t.tz(tz.name).format("YYYY-MM-DD") != t.tz(local_tz).format("YYYY-MM-DD") ? "datetimeformat" : "timeformat";
            var time_str = t.tz(local_tz).format($("body").data(format));
            var $add = $("<small>").addClass("text-muted").append(" (" + gettext("Your local time:") + " ")
            $add.append($('<time>').attr("datetime", time_str).text(time_str))
            $add.append(" " + moment.tz.zone(local_tz).abbr(t) + ")");
            $add.insertAfter($(this));
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
    (function() {
        var dialog = document.getElementById("lightbox-dialog");
        var img = dialog.querySelector("img");
        var caption = dialog.querySelector("figcaption");
        $(dialog).on("mousedown", function (e) {
            if (e.target == this) {
                // dialog has no padding, so click triggers only on backdrop
                this.close();
            }
        });
        $("a[data-lightbox]").on("click", function (e) {
            e.preventDefault();
            var label = this.querySelector("img").alt;
            img.src = this.href;
            img.alt = label;
            caption.textContent = label;
            dialog.showModal();
        });
    })();



    // free-range price input auto-check checkbox/set count-input to 1 if 0
    $("[data-checked-onchange]").each(function() {
        var countInput = this;
        $("#" + this.getAttribute("data-checked-onchange")).on("input", function() {
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

    $("#customer-account-login-providers a").click(function () {
        // Prevent double-submit, see also https://github.com/pretix/pretix/issues/5836
        $(this).addClass("disabled");
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
                // save answer as data-attribute so if external event changes select-element/options it can select correct entries
                // currently used when country => state changes
                var answer = answers.filter("[name$=" + suffix + "]").find(":selected").val();
                input.prop("data-selected-value", answer).val(answer).change();
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
