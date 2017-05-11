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

$(function () {
    "use strict";
    $("input[data-toggle=radiocollapse]").change(function () {
        $($(this).attr("data-parent")).find(".collapse.in").collapse('hide');
        $($(this).attr("data-target")).collapse('show');
    });
    $(".js-only").removeClass("js-only");
    $(".js-hidden").hide();
    $(".variations-collapsed").hide();
    $("a[data-toggle=variations]").click(function (e) {
        $(this).parent().parent().parent().find(".variations").slideToggle();
        e.preventDefault();
    });
    $(".collapsed").removeClass("collapsed").addClass("collapse");

    $("#voucher-box").hide();
    $("#voucher-toggle").show();
    $("#voucher-toggle a").click(function () {
        $("#voucher-box").slideDown();
        $("#voucher-toggle").slideUp();
    });
    
    $('[data-toggle="tooltip"]').tooltip();

    $("#ajaxerr").on("click", ".ajaxerr-close", ajaxErrDialog.hide);

    // AddOns
    $('.addon-variation-description').hide();
    $('.toggle-variation-description').click(function () {
        $(this).parent().find('.addon-variation-description').slideToggle();
    });
    
    // Copy answers
    $(".js-copy-answers").click(function (e) {
        e.preventDefault();
        var idx = $(this).data('id');
        copy_answers(idx);
    });

    // Lightbox
    lightbox.init();
});

function copy_answers(idx) {    
    var elements = $('*[data-idx="'+idx+'"] input, *[data-idx="'+idx+'"] select, *[data-idx="'+idx+'"] textarea');
    var firstAnswers = $('*[data-idx="0"] input, *[data-idx="0"] select, *[data-idx="0"] textarea');
    elements.each(function(index){
        var input = $(this),
            tagName = input.prop('tagName').toLowerCase(),
            attributeType = input.attr('type');

        switch (tagName) {
            case "textarea":            
                input.val(firstAnswers.eq(index).val());
                break;
            case "select":
                input.val(firstAnswers.eq(index).find(":selected").val()).change();
                break;
            case "input":
                switch (attributeType) {
                    case "text":
                    case "number":
                        input.val(firstAnswers.eq(index).val());
                        break;
                    case "checkbox":
                    case "radio":
                        input.prop("checked", firstAnswers.eq(index).prop("checked"));
                        break;
                    default:
                        input.val(firstAnswers.eq(index).val());
                } 
                break;
            default:
                input.val(firstAnswers.eq(index).val());
        } 
    });
}
