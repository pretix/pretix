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
    $("div.collapsed").removeClass("collapsed").addClass("collapse");
    $(".has-error").each(function () {
        $(this).closest("div.panel-collapse").collapse("show");
    });

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
        e.stopPropagation();
        var idx = $(this).data('id');
        copy_answers(idx);
        return false;
    });

    // Subevent choice
    if ($(".subevent-toggle").length) {
        $(".subevent-list").hide();
        $(".subevent-toggle").css("display", "block").click(function() {
            $(".subevent-list").slideToggle(300);
        });
    }

    $("#monthselform select").change(function () {
        $(this).closest("form").get(0).submit();
    });

    var update_cart_form = function () {
        var is_enabled = $(".product-row input[type=checkbox]:checked, .variations input[type=checkbox]:checked, .product-row input[type=radio]:checked, .variations input[type=radio]:checked").length;
        if (!is_enabled) {
            $(".input-item-count").each(function() {
                if ($(this).val() && $(this).val() !== "0") {
                    is_enabled = true;
                }
            });
        }
        $("#btn-add-to-cart").prop("disabled", !is_enabled);
    };
    update_cart_form();
    $(".product-row input[type=checkbox], .variations input[type=checkbox], .product-row input[type=radio], .variations input[type=radio], .input-item-count").on("change mouseup keyup", update_cart_form);

    $(".table-calendar td.has-events").click(function () {
        var $tr = $(this).closest(".table-calendar").find(".selected-day");
        $tr.find("td").html($(this).find(".events").html());
        $tr.find("td").prepend($("<h3>").text($(this).attr("data-date")));
        $tr.show();
    });

    // Invoice address form
    $("input[data-required-if]").each(function () {
      var dependent = $(this),
        dependency = $($(this).attr("data-required-if")),
        update = function (ev) {
          var enabled = (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val();
          dependent.prop('required', enabled).closest('.form-group').toggleClass('required', enabled);
        };
      update();
      dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("change", update);
      dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("dp.change", update);
    });

    $("input[data-display-dependency]").each(function () {
        var dependent = $(this),
            dependency = $($(this).attr("data-display-dependency")),
            update = function (ev) {
                var enabled = (dependency.attr("type") === 'checkbox' || dependency.attr("type") === 'radio') ? dependency.prop('checked') : !!dependency.val();
                if (ev) {
                    dependent.closest('.form-group').slideToggle(enabled);
                } else {
                    dependent.closest('.form-group').toggle(enabled);
                }
            };
        update();
        dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("change", update);
        dependency.closest('.form-group').find('input[name=' + dependency.attr("name") + ']').on("dp.change", update);
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
            attributeType = input.attr('type'),
            suffix = input.attr('name').split('-')[1];


        switch (tagName) {
            case "textarea":
                input.val(firstAnswers.filter("[name$=" + suffix + "]").val());
                break;
            case "select":
                input.val(firstAnswers.filter("[name$=" + suffix + "]").find(":selected").val()).change();
                break;
            case "input":
                switch (attributeType) {
                    case "text":
                    case "number":
                        input.val(firstAnswers.filter("[name$=" + suffix + "]").val());
                        break;
                    case "checkbox":
                    case "radio":
                        input.prop("checked", firstAnswers.filter("[name$=" + suffix + "]").prop("checked"));
                        break;
                    default:
                        input.val(firstAnswers.filter("[name$=" + suffix + "]").val());
                } 
                break;
            default:
                input.val(firstAnswers.filter("[name$=" + suffix + "]").val());
        } 
    });
}
