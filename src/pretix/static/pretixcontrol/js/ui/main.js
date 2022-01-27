/*global $,gettext*/

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

var apiGET = function (url, callback) {
    $.getJSON(url, function (data) {
        callback(data);
    });
};

var i18nToString = function (i18nstring) {
    var locale = $("body").attr("data-pretixlocale");
    if (i18nstring[locale]) {
        return i18nstring[locale];
    } else if (i18nstring["en"]) {
        return i18nstring["en"];
    }
    for (key in i18nstring) {
        if (i18nstring[key]) {
            return i18nstring[key];
        }
    }
};

$(document).ajaxError(function (event, jqXHR, settings, thrownError) {
    waitingDialog.hide();
    var c = $(jqXHR.responseText).filter('.container');
    if (c.length > 0) {
        ajaxErrDialog.show(c.first().html());
    } else if (thrownError !== "abort" && thrownError !== "") {
        console.log(thrownError);
        alert(gettext('Unknown error.'));
    }
});

var form_handlers = function (el) {
    el.find("[data-formset]").formset(
        {
            animateForms: true,
            reorderMode: 'animate'
        }
    );
    el.find("[data-formset]").on("formAdded", "div", function (event) {
        form_handlers($(event.target));
    });

    // Vouchers
    el.find("#voucher-bulk-codes-generate").click(function () {
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
            setTimeout(function () {
                $(".form-group:has(#voucher-bulk-codes-num)").removeClass("has-error");
            }, 3000);
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
        if ($(this).is('[data-min]')) {
            opts["minDate"] = $(this).attr("data-min");
            opts["viewDate"] = $(this).attr("data-min");
        }
        if ($(this).is('[data-max]')) {
            opts["maxDate"] = $(this).attr("data-max");
            opts["viewDate"] = $(this).attr("data-max");
        }
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
        if ($(this).is('[data-is-payment-date]'))
            opts["daysOfWeekDisabled"] = JSON.parse($("body").attr("data-payment-weekdays-disabled"));
        $(this).datetimepicker(opts);
    });

    el.find(".datetimepicker[data-date-after], .datepickerfield[data-date-after]").each(function () {
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

    el.find(".datetimepicker[data-date-default], .datepickerfield[data-date-default]").each(function () {
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

    function luminanace(r, g, b) {
        var a = [r, g, b].map(function (v) {
            v /= 255;
            return v <= 0.03928
                ? v / 12.92
                : Math.pow( (v + 0.055) / 1.055, 2.4 );
        });
        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
    }
    function contrast(rgb1, rgb2) {
        var l1 = luminanace(rgb1[0], rgb1[1], rgb1[2]) + 0.05,
             l2 = luminanace(rgb2[0], rgb2[1], rgb2[2]) + 0.05,
             ratio = l1/l2
        if (l2 > l1) {ratio = 1/ratio}
        return ratio.toFixed(1)
    }
    el.find(".colorpickerfield").colorpicker({
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
    }).on('changeColor create', function (e) {
        var rgb = $(this).colorpicker('color').toRGB();
        var c = contrast([255,255,255], [rgb.r, rgb.g, rgb.b]);
        var mark = 'times';
        if ($(this).parent().find(".contrast-state").length === 0) {
            $(this).parent().append("<div class='help-block contrast-state'></div>");
        }
        var $note = $(this).parent().find(".contrast-state");
        if ($(this).val() === "") {
            $note.remove();
        }
        if (!$(this).is(".no-contrast")) {
            if (c > 7) {
                $note.html("<span class='fa fa-fw fa-check-circle'></span>")
                    .append(gettext('Your color has great contrast and is very easy to read!'));
                $note.addClass("text-success").removeClass("text-warning").removeClass("text-danger");
            } else if (c > 2.5) {
                $note.html("<span class='fa fa-fw fa-info-circle'></span>")
                    .append(gettext('Your color has decent contrast and is probably good-enough to read!'));
                $note.removeClass("text-success").removeClass("text-warning").removeClass("text-danger");
            } else {
                $note.html("<span class='fa fa-fw fa-warning'></span>")
                    .append(gettext('Your color has bad contrast for text on white background, please choose a darker ' +
                        'shade.'));
                $note.addClass("text-danger").removeClass("text-success").removeClass("text-warning");
            }
        }
    });

    el.find("input[data-checkbox-dependency]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-checkbox-dependency")),
            update = function () {
                var enabled = dependency.prop('checked');
                dependent.prop('disabled', !enabled).closest('.form-group, .form-field-boundary').toggleClass('disabled', !enabled);
                if (!enabled && !$(this).is('[data-checkbox-dependency-visual]')) {
                    dependent.prop('checked', false);
                }
            };
        update();
        dependency.on("change", update);
    });

    el.find("select[data-inverse-dependency], input[data-inverse-dependency]").each(function () {
        var dependency = $(this).attr("data-inverse-dependency");
        if (dependency.substr(0, 1) === '<') {
            dependency = $(this).closest("form, .form-horizontal").find(dependency.substr(1));
        } else {
            dependency = $(dependency);
        }

        var dependent = $(this),
            update = function () {
                var enabled = !dependency.prop('checked');
                dependent.prop('disabled', !enabled).closest('.form-group, .form-field-boundary').toggleClass('disabled', !enabled);
            };
        update();
        dependency.on("change", update);
    });

    el.find("div[data-display-dependency], textarea[data-display-dependency], input[data-display-dependency], select[data-display-dependency]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-display-dependency")),
            update = function (ev) {
                var enabled = dependency.toArray().some(function(d) {return (d.type === 'checkbox' || d.type === 'radio') ? d.checked : !!d.value;});
                if (dependent.is("[data-inverse]")) {
                    enabled = !enabled;
                }
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
        dependency.closest('.form-group').find('[name=' + dependency.attr("name") + ']').on("change", update);
        dependency.closest('.form-group').find('[name=' + dependency.attr("name") + ']').on("dp.change", update);
    });

    el.find("input[data-required-if], select[data-required-if], textarea[data-required-if]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-required-if")),
            update = function (ev) {
                var enabled = (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val();
                dependent.prop('required', enabled).closest('.form-group').toggleClass('required', enabled).find('.optional').stop().animate({
                    'opacity': enabled ? 0 : 1
                }, ev ? 500 : 1);
            };
        update();
        dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("change", update);
        dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("dp.change", update);
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

    $("select[name$=state]:not([data-static])").each(function () {
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

    el.find("div.scrolling-multiple-choice").each(function () {
        if ($(this).find(".choice-options-all").length > 0) {
            return;
        }
        var $menu = $("<div>").addClass("choice-options-menu");
        var $a_all = $("<a>").addClass("choice-options-all").attr("href", "#").text(gettext("All"));
        var $a_none = $("<a>").addClass("choice-options-none").attr("href", "#").text(gettext("None"));
        var $inp_search = $("<input>").addClass("form-control").attr("type", "text").attr("placeholder", gettext("Search query"));
        var $lbl_tgl = $("<div>").addClass("checkbox menu-checkbox");
        var $cb_tgl = $("<input>").attr("type", "checkbox").addClass("menu-checkbox");
        $lbl_tgl.append($("<label>").append($cb_tgl).append(gettext("Selected only")));
        $menu.append($("<span>").append($a_all).append(" / ").append($a_none))
        if (!$(this).is(".no-search")) {
            $menu.append($inp_search);
            $menu.append($lbl_tgl);
        }
        $(this).prepend($menu);

        $(this).find(".choice-options-none").click(function (e) {
            $(this).closest(".scrolling-multiple-choice").find("input[type=checkbox]:not(.menu-checkbox)").prop("checked", false);
            $cb_tgl.trigger("change");
            e.preventDefault();
            return false;
        });
        $(this).find(".choice-options-all").click(function (e) {
            $(this).closest(".scrolling-multiple-choice").find("input[type=checkbox]:not(.menu-checkbox)").prop("checked", true);
            $cb_tgl.trigger("change");
            e.preventDefault();
            return false;
        });
        $cb_tgl.on("change", function (e) {
            var tgl = $cb_tgl.prop("checked");

            $(this).closest(".scrolling-multiple-choice").find("div.checkbox:not(.menu-checkbox)").each(function () {
                $(this).toggleClass("sr-only", tgl && !$(this).find("input[type=checkbox]").prop("checked"));
            })
        });
        $inp_search.on("keyup change", function (e) {
            var term = $inp_search.val().toLowerCase();

            $(this).closest(".scrolling-multiple-choice").find("div.checkbox:not(.menu-checkbox)").each(function () {
                $(this).toggleClass("hidden", !$(this).text().toLowerCase().includes(term));
            })
        })
    });

    el.find('.select2-static').select2({
        theme: "bootstrap",
        language: $("body").attr("data-select2-locale"),
    });

    el.find('input[data-typeahead-url]').each(function () {
        var $inp = $(this);
        $inp.typeahead(null, {
            minLength: 1,
            highlight: true,
            source: new Bloodhound({
                datumTokenizer: Bloodhound.tokenizers.obj.whitespace('value'),
                queryTokenizer: Bloodhound.tokenizers.whitespace,
                remote: {
                    url: $inp.attr("data-typeahead-url"),
                    prepare: function (query, settings) {
                        var sep = (settings.url.indexOf('?') > 0) ? '&' : '?';
                        settings.url = settings.url + sep + 'q=' + encodeURIComponent(query);
                        return settings;
                    },
                    transform: function (object) {
                        var results = object.results;
                        var suggs = [];
                        var reslen = results.length;
                        for (var i = 0; i < reslen; i++) {
                            suggs.push(results[i]);
                        }
                        return suggs;
                    }
                }
            }),
            display: function (obj) {
                return obj.name;
            },
        });
    });

    el.find('[data-model-select2=generic]').each(function () {
        var $s = $(this);
        $s.select2({
            theme: "bootstrap",
            delay: 100,
            allowClear: !$s.prop("required"),
            width: '100%',
            language: $("body").attr("data-select2-locale"),
            placeholder: $(this).attr("data-placeholder"),
            ajax: {
                url: $(this).attr('data-select2-url'),
                data: function (params) {
                    return {
                        query: params.term,
                        page: params.page || 1
                    }
                }
            },
            templateResult: function (res) {
                if (!res.id) {
                    return res.text;
                }
                var $ret = $("<span>").append(
                    $(res.inactive ? "<strike class='text-muted'>" : "<span>").addClass("primary").append($("<div>").text(res.text).html())
                );
                if (res.event) {
                    $ret.append(
                        $("<span>").addClass("secondary").append(
                            $("<span>").addClass("fa fa-calendar fa-fw")
                        ).append(" ").append($("<div>").text(res.event).html())
                    );
                }
                return $ret;
            },
        }).on("select2:select", function () {
            // Allow continuing to select
            if ($s.hasAttribute("multiple")) {
                window.setTimeout(function () {
                    $s.parent().find('.select2-search__field').focus();
                }, 50);
            }
        });
    });

    el.find('[data-model-select2=event]').each(function () {
        var $s = $(this);
        $s.select2({
            theme: "bootstrap",
            delay: 100,
            allowClear: !$s.prop("required"),
            width: '100%',
            language: $("body").attr("data-select2-locale"),
            ajax: {
                url: $(this).attr('data-select2-url'),
                data: function (params) {
                    return {
                        query: params.term,
                        page: params.page || 1
                    }
                }
            },
            placeholder: $(this).attr("data-placeholder"),
            templateResult: function (res) {
                if (!res.id) {
                    return res.text;
                }
                var $ret = $("<span>").append(
                    $("<span>").addClass("event-name-full").append($("<div>").text(res.name).html())
                );
                if (res.organizer) {
                    $ret.append(
                        $("<span>").addClass("event-organizer").append(
                            $("<span>").addClass("fa fa-users fa-fw")
                        ).append(" ").append($("<div>").text(res.organizer).html())
                    );
                }
                $ret.append(
                    $("<span>").addClass("event-daterange").append(
                        $("<span>").addClass("fa fa-calendar fa-fw")
                    ).append(" ").append(res.date_range)
                );
                return $ret;
            },
        }).on("select2:select", function () {
            // Allow continuing to select
            window.setTimeout(function () {
                $s.parent().find('.select2-search__field').focus();
            }, 50);
        });
    });

    el.find(".simple-subevent-choice").change(function () {
        $(this).closest("form").submit();
    });

    el.find("input[name=basics-slug]").bind("keyup keydown change", function () {
        $(this).closest(".form-group").find(".slug-length").toggle($(this).val().length > 16);
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

    el.find(".bulk-edit-field-group").each(function () {
        var $checkbox = $(this).find("input[type=checkbox][name=_bulk]");
        var $content = $(this).find(".field-content");
        var $fields = $content.find("input, select, textarea, button");

        var update = function () {
            var isChecked = $checkbox.prop("checked");
            $content.toggleClass("enabled", isChecked);
            $fields.attr("tabIndex", isChecked ? 0 : -1);
        }
        $content.on("focusin change click", function () {
            if ($checkbox.prop("checked")) return;
            $checkbox.prop("checked", true);
            update();
        });
        $checkbox.on('change', update)
        update();
    });

    el.find("input[name*=question], select[name*=question]").change(questions_toggle_dependent);
    questions_toggle_dependent();
    questions_init_photos(el);
};

$(function () {
    "use strict";

    $("body").removeClass("nojs");
    lightbox.init();

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
    $("input[data-toggle=radiocollapse]").change(function () {
        $($(this).attr("data-parent")).find(".collapse.in").collapse('hide');
        $($(this).attr("data-target")).collapse('show');
    });
    $("div.collapsed").removeClass("collapsed").addClass("collapse");
    $(".has-error").each(function () {
        $(this).closest("div.panel-collapse").collapse("show");
    });

    $('[data-toggle="tooltip"]').tooltip();
    $('[data-toggle="tooltip_html"]').tooltip({
        'html': true,
        'whiteList': {
            // Global attributes allowed on any supplied element below.
            '*': ['class', 'dir', 'id', 'lang', 'role'],
            b: [],
            br: [],
            code: [],
            div: [],  // required for template
            h3: ['class', 'role'],  // required for template
            i: [],
            small: [],
            span: [],
            strong: [],
            u: [],
        }
    });

    var url = document.location.toString();
    if (url.match('#')) {
        $('.nav-tabs a[href="#' + url.split('#')[1] + '"]').tab('show');
    }
    $('a[data-toggle="tab"]').on('click', function (e) {
        if (!$(this).closest(".tab-content").length) {
            // only append hash if not inside a .panel
            window.location.hash = this.hash;
        }
    });

    // Event wizard
    $("#event-slug-random-generate").click(function () {
        var url = $(this).attr("data-rng-url");
        $("#id_basics-slug").val("Generating...");
        $.getJSON(url, function (data) {
            $("#id_basics-slug").val(data.slug);
        });
    });

    form_handlers($("body"));
    $(document).trigger("pretix:bind-forms");

    $(".qrcode-canvas").each(function () {
        $(this).qrcode(
            {
                text: $.trim($($(this).attr("data-qrdata")).html())
            }
        );
    });

    $(".propagated-settings-box").find("input, textarea, select").not("[readonly]")
        .attr("data-propagated-locked", "true").prop("readonly", true);

    $(".propagated-settings-box button[data-action=unlink]").click(function (ev) {
        var $box = $(this).closest(".propagated-settings-box");
        $box.find("[data-propagated-locked]").prop("readonly", false);
        $box.removeClass("locked").addClass("unlocked");
        ev.preventDefault();
        return true;
    });

    // Tables with bulk selection, e.g. subevent list
    $("input[data-toggle-table]").each(function (ev) {
        var $toggle = $(this);
        var $actionButtons = $(".batch-select-actions button", this.form);
        var countLabels = $("<span></span>").appendTo($actionButtons);
        var $table = $toggle.closest("table");
        var $selectAll = $table.find(".table-select-all");
        var $rows = $table.find("tbody tr");
        var $checkboxes = $rows.find("td:first-child input[type=checkbox]");
        var firstIndex, lastIndex, selectionChecked, onChangeSelectionHappened = false;
        var updateSelection = function(a, b, checked) {
            if (a > b) {
                //[a, b] = [b, a];// ES6 not ready yet for pretix
                var tmp = a;
                a = b;
                b = tmp;
            }
            for (var i = a; i <= b; i++) {
                var checkbox = $checkboxes.get(i);
                if (!checkbox.hasAttribute("data-inital")) checkbox.setAttribute("data-inital", checkbox.checked);
                if (checked === undefined || checked === null) checkbox.checked = checkbox.getAttribute("data-inital") === "true";
                else checkbox.checked = checked;
            }
        };
        var onChangeSelection = function(ev) {
            onChangeSelectionHappened = true;

            var row = ev.target.closest("tr");
            var currentIndex = 0;
            while(row = row.previousSibling) {
                if (row.tagName) currentIndex++;
            }
            var dCurrent = currentIndex - firstIndex;
            var dLast = lastIndex - firstIndex;
            if (dCurrent*dLast < 0) {
                // direction of selection changed => reset all previously selected
                updateSelection(lastIndex, firstIndex);
            }
            else if (Math.abs(dCurrent) < Math.abs(dLast)) {
                // selection distance decreased => reset unselected
                updateSelection(currentIndex, lastIndex);
            }
            lastIndex = currentIndex;
            updateSelection(firstIndex, currentIndex, selectionChecked);

            ev.preventDefault();
        };
        $table.on("pointerdown", function(ev) {
            if (!ev.target.closest("td:first-child")) return;
            var row = ev.target.closest("tr");
            selectionChecked = !row.querySelector("td:first-child input").checked;

            firstIndex = 0;
            while(row = row.previousSibling) {
                if (row.tagName) firstIndex++;
            }
            lastIndex = firstIndex;

            ev.preventDefault();
            $rows.on("pointerenter", onChangeSelection);

            $(document).one("pointerup", function(ev) {
                if (onChangeSelectionHappened) {
                    ev.preventDefault();
                    onChangeSelectionHappened = false;
                    $checkboxes.removeAttr("data-inital");

                    update();
                }
                $rows.off("pointerenter", onChangeSelection);
            });
        });

        var update = function() {
            var nrOfChecked = $checkboxes.filter(":checked").length;
            var allChecked = nrOfChecked == $checkboxes.length;

            if (!nrOfChecked) countLabels.empty();
            else countLabels.text(" ("+nrOfChecked+")");

            if (!allChecked) $selectAll.find("input").prop("checked", false); 

            $actionButtons.attr("disabled", !nrOfChecked);
            $toggle.prop("checked", allChecked).prop("indeterminate", nrOfChecked > 0 && !allChecked);
            $selectAll.toggleClass("hidden", nrOfChecked !== $checkboxes.length).prop("hidden", nrOfChecked !== $checkboxes.length);

        }

        $checkboxes.change(update);
        $toggle.change(function (ev) {
            this.indeterminate = false;
            $checkboxes.prop("checked", this.checked);
            update();
        });
        $selectAll.find("input").change(function(ev) {
            if (this.checked) countLabels.text(" ("+this.getAttribute("data-results-total")+")");
            else countLabels.text(" ("+$checkboxes.filter(":checked").length+")");
        })

        update();
    });

    // Items and categories
    $(".internal-name-wrapper").each(function () {
        if ($(this).find("input").val() === "") {
            var $fg = $(this).find(".form-group");
            $fg.hide();
            var $fgl = $("<div>").addClass("form-group").append(
                $("<div>").addClass("col-md-9 col-md-offset-3").append(
                    $("<div>").addClass("help-block").append(
                        $("<a>").attr("href", "#").text(
                            gettext("Use a different name internally")
                        ).click(function () {
                            $fg.slideDown();
                            $fgl.slideUp();
                            return false;
                        })
                    )
                )
            );
            $(this).append($fgl);
        }
    });

    $("button[data-toggle=qrcode]").click(function (e) {
        e.preventDefault();
        var $current = $(".qr-code-overlay[data-qrcode='" + $(this).attr("data-qrcode") + "']");
        if ($current.length) {
            $(".qr-code-overlay").attr("data-qrcode", "").slideUp(200);
            return false;
        }
        $(".qr-code-overlay").remove();
        var $div = $("<div>").addClass("qr-code-overlay").attr("data-qrcode", $(this).attr("data-qrcode"));
        $div.appendTo($("body"));
        var offset = $(this).offset();
        $div.css("top", offset.top + $(this).outerHeight() + 10).css("left", offset.left);
        var $child = $("<div>");
        $child.appendTo($div);
        $child.qrcode(
            {
                text: $(this).attr("data-qrcode"),
                correctLevel: 0,  // M
                width: 196,
                height: 196
            }
        );
        $div.append($(this).attr("data-qrcode").slice(0, 10) + "…<br>");
        $div.append(gettext("Click to close"));
        $div.slideDown(200);
        $div.click(function (e) {
            $(".qr-code-overlay").attr("data-qrcode", "").slideUp(200);
        });
        return false;
    });

    $("#ajaxerr").on("click", ".ajaxerr-close", ajaxErrDialog.hide);
    moment.locale($("body").attr("data-datetimelocale"));
    add_log_expand_handlers($("body"));
});

function add_log_expand_handlers(el) {
    el.find("a[data-expandlogs], a[data-expandrefund], a[data-expandpayment]").click(function (e) {
        e.preventDefault();
        var $a = $(this);
        var id = $(this).attr("data-id");
        $a.find(".fa").removeClass("fa-eye").addClass("fa-cog fa-spin");
        var url = '/control/logdetail/';
        if ($a.is("[data-expandrefund]")) {
            url += 'refund/'
        } else if ($a.is("[data-expandpayment]")) {
            url += 'payment/'
        }
        $.getJSON(url + '?pk=' + id, function (data) {
            if ($a.parent().tagName === "p") {
                $("<pre>").text(JSON.stringify(data.data, null, 2)).insertAfter($a.parent());
            } else {
                $("<pre>").text(JSON.stringify(data.data, null, 2)).appendTo($a.parent());
            }
            $a.remove();
        });
        return false;
    });

}

$(document).ready(function () {
   $('form[method=post]').filter(function () {
       return $(this).find("button:not([type=button]), input[type=submit]").length > 0;
   }).areYouSure( {'message': gettext('You have unsaved changes!')});
});
