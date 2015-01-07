"use strict";
$(function () {
    $("[data-formset]").formset({
        animateForms: true,
        reorderMode: 'animate'
    });
    $(document).on("click", ".variations .variations-select-all", function (e) {
        $(this).parent().parent().find("input[type=checkbox]").prop("checked", true);
        e.stopPropagation();
        return false;
    });
    $(document).on("click", ".variations .variations-select-none", function (e) {
        $(this).parent().parent().find("input[type=checkbox]").prop("checked", false);
        e.stopPropagation();
        return false;
    });
    $('.collapse').collapse();
});
