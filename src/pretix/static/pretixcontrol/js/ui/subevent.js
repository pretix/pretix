/*globals $, Morris, gettext, RRule, RRuleSet*/

$(function () {
    if (!$("div[data-formset-prefix=checkinlist_set]").length) {
        return;
    }

    function parse_weekday(wd) {
        map = {
            'MO': 0,
            'TU': 1,
            'WE': 2,
            'TH': 3,
            'FR': 4,
            'SA': 5,
            'SU': 6
        }
        if (wd.indexOf(",") > 0) {
            var wds = [];
            $.each(wd.split(","), function (k, v) {
                wds.push(map[v]);
            });
            return wds;
        } else {
            return map[wd];
        }
    }

    function rrule_preview() {
        var ruleset = new RRuleSet();

        $(".rrule-form").each(function () {
            if ($(this).find("input[name$=DELETE]").prop("checked")) {
                return;
            }

            var rule_args = {};
            var $form = $(this);
            var freq = $form.find("select[name*=freq]").val();
            if (!$form.find("input[name*=dtstart]").data("DateTimePicker")) {
                // uninitialized
                return;
            }
            var dtstart = $form.find("input[name*=dtstart]").data("DateTimePicker").date();
            dtstart = dtstart.add(dtstart.utcOffset(), 'm').add(12, 'h').utcOffset(0);
            rule_args.dtstart = dtstart.toDate();
            rule_args.interval = parseInt($form.find("input[name*=interval]").val()) || 1;

            if (freq === 'yearly') {
                rule_args.freq = RRule.YEARLY;

                var same = $form.find("input[name*=yearly_same]:checked").val();
                if (same === "off") {
                    rule_args.bysetpos = parseInt($form.find("select[name*=yearly_bysetpos]").val());
                    rule_args.byweekday = parse_weekday($form.find("select[name*=yearly_byweekday]").val());
                    rule_args.bymonth = parseInt($form.find("select[name*=yearly_bymonth]").val());
                }
            } else if (freq === 'monthly') {
                rule_args.freq = RRule.MONTHLY;

                var same = $form.find("input[name*=monthly_same]:checked").val();
                if (same === "off") {
                    rule_args.bysetpos = parseInt($form.find("select[name*=monthly_bysetpos]").val());
                    rule_args.byweekday = parse_weekday($form.find("select[name*=monthly_byweekday]").val());
                }
            } else if (freq === 'weekly') {
                rule_args.freq = RRule.WEEKLY;

                var days = [];
                $form.find("input[name*=weekly_byweekday]:checked").each(function () {
                    days.push(parse_weekday($(this).val()));
                });
                if (days.length !== 0) {
                    rule_args.byweekday = days;
                }
            } else if (freq === 'daily') {
                rule_args.freq = RRule.DAILY;
            }

            var end = $form.find("input[name*=end]:checked").val();
            if (end === "count") {
                rule_args.count = parseInt($form.find("input[name*=count]").val()) || 1;
            } else {
                var date = $form.find("input[name*=until]").data("DateTimePicker").date();
                if (date !== null) {
                    rule_args.until = date.toDate();
                }
            }

            if ($form.find("input[name*=exclude]").prop("checked")) {
                ruleset.exrule(new RRule(rule_args));
                $form.closest(".panel").addClass("panel-danger").removeClass("panel-default");
            } else {
                ruleset.rrule(new RRule(rule_args));
                $form.closest(".panel").addClass("panel-default").removeClass("panel-danger");
            }
        });

        var all_dates = ruleset.all();
        var format = $("body").attr("data-longdateformat") + " (dddd)";
        $("#rrule-preview").html("");
        if (all_dates.length > 20) {
            $("#rrule-preview").html("");
            all_dates.slice(0, 10).forEach(function(element) {
                $("#rrule-preview").append($("<li>").text(moment(element).utc().format(format)));
            });
            $("#rrule-preview").append($("<li>").text(ngettext(
                    "(one more date)",
                    "({num} more dates)",
                    all_dates.length - 20
            ).replace(/\{num\}/g, all_dates.length - 20)));
            all_dates.slice(-10).forEach(function(element) {
                $("#rrule-preview").append($("<li>").text(moment(element).utc().format(format)));
            });
        } else {
            all_dates.forEach(function(element) {
                $("#rrule-preview").append($("<li>").text(moment(element).utc().format(format)));
            });
        }
    }

    function rrule_form_toggles($form) {
        var freq = $form.find("select[name*=freq]").val();
        $form.find(".repeat-yearly").toggle(freq === "yearly");
        $form.find(".repeat-monthly").toggle(freq === "monthly");
        $form.find(".repeat-weekly").toggle(freq === "weekly");
    }

    function rrule_bind_form($form) {
        $form.find("select[name*=freq]").change(function () {
            rrule_form_toggles($form);
        });
        rrule_form_toggles($form);
    }

    $("#rrule-formset").on("change keydown keyup keypress dp.change", "input, select", function () {
        rrule_preview();
    });
    rrule_preview();

    $(".rrule-form").each(function () { rrule_bind_form($(this)); });
    $("#rrule-formset").on("formAdded", "div", function (event) { rrule_bind_form($(event.target)); });

    var $namef = $("input[id^=id_name]").first();
    var lastValue = $namef.val();
    $namef.change(function () {
        var field = $("div[data-formset-prefix=checkinlist_set] input[id$=name]").first();
        if (field.val() === lastValue) {
            lastValue = $(this).val();
            field.val(lastValue);
        }
    });
});
