/*globals $, Morris, gettext, RRule, RRuleSet*/
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


$(document).on("pretix:bind-forms", function () {
    $(".rrule-form").each(function () {
        rrule_bind_form($(this));
    });
});
