/*global $*/

$(function () {
    "use strict";

    var nested_formset_config = {
        form: '[data-nested-formset-form]',
        emptyForm: 'script[type=form-template][data-nested-formset-empty-form]',
        body: '[data-nested-formset-body]',
        add: '[data-nested-formset-add]',
        deleteButton: '[data-nested-formset-delete-button]',
        moveUpButton: '[data-nested-formset-move-up-button]',
        moveDownButton: '[data-nested-formset-move-down-button]',
        animateForms: true,
        reorderMode: 'animate',
        empty_prefix: '__inner_prefix__'
    };
    $("[data-formset]").formset(
        {
            animateForms: true,
            reorderMode: 'animate'
        }
    ).on("formAdded", "[data-formset-form]", function () {
        $(this).find(".nested-formset").formset(nested_formset_config);
    });
    $(".nested-formset").formset(nested_formset_config);
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
