"use strict";
$(function () {
    $("[data-formset]").formset({
        animateForms: true,
        reorderMode: 'animate'
    });
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
        $(".table-product-overview .sum").toggle($(this).attr("data-target") === ".sum");
        $("#sumtoggle").find("button").not($(this)).removeClass("active");
        $(this).addClass("active");
        $(".table-product-overview .count").toggle($(this).attr("data-target") === ".count");
    });

    $('.collapsible').collapse();
});
