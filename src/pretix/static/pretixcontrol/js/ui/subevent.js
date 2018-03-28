/*globals $, Morris, gettext*/

$(function () {
    if (!$("div[data-formset-prefix=checkinlist_set]").length) {
        return;
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

    $(".rrule-form").each(function () { rrule_bind_form($(this)); });
    // TODO: <$("#rrule-formset").bind("formAdded", ticket_type_quota_calculation);

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
