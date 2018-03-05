/*globals $, Morris, gettext*/
$(function () {
    if (!$("div[data-formset-prefix=checkinlist_set]").length) {
        return;
    }

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
