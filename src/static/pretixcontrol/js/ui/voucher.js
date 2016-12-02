/*globals $, Morris, gettext*/
$(function () {
    if (!$("#voucher-create").length) {
        return;
    }

    function show_step(state_el) {
        var was_visible = state_el.is(':visible');
        state_el.animate({
            'height': 'show',
            'opacity': 'show',
            'padding-top': 'show',
            'padding-bottom': 'show',
            'margin-top': 'show',
            'margin-bottom': 'show'
        }, 400);
        var offset = state_el.offset();
        var body = $("html, body");
        if (!was_visible && offset.top > $("body").scrollTop() + $(window).height() - 160) {
            body.animate({scrollTop: offset.top + 200}, '400', 'swing');
        }
    }

    if ($(".alert-danger").length === 0) {
        $(".wizard-step, .wizard-advanced, #step-save").hide();
        $(".wizard-step").first().show();
    }

    $("#id_number, #id_max_usages").on("change keydown keyup", function () {
        if ($("#id_number").val() && $("#id_max_usages").val()) {
            show_step($("#step-valid"));
        }
    });

    $("#id_valid_until").on("focus change", function () {
        $("input[name=has_valid_until][value=no]").prop("checked", false);
        $("input[name=has_valid_until][value=yes]").prop("checked", true);
    }).on("change dp.change", function () {
        if ($("input[name=has_valid_until][value=no]").prop("checked") || $("#id_valid_until").val()) {
            show_step($("#step-products"));
        } 
    });

    $("input[name=has_valid_until]").on("change", function () {
        if ($("input[name=has_valid_until]").not("[value=on]").prop("checked") || $("#id_valid_until").val()) {
            show_step($("#step-products"));
        } else {
            $("#id_valid_until").focus();
        }
    });

    $("input[name=itemvar]").on("change", function () {
        show_step($("#step-price"));
    });

    $("#step-price input").on("change keydown keyup", function () {
        var mode = $("input[name=price_mode]:checked").val();
        var show_next = (mode === 'none' || $("input[name='value_" + mode + "']").val());
        if (show_next) {
            show_step($("#step-block"));
        } else {
            $("input[name='value_" + mode + "']").focus();
        }
    });
    $("#step-price input[type=text]").on("focus change keyup keydown", function () {
        $("#step-price input[type=radio]").prop("checked", false);
        $(this).closest(".radio").find("input[type=radio]").prop("checked", true);
    });

    $("input[name=block_quota]").on("change", function () {
        show_step($("#step-advanced"));
        show_step($("#step-save"));
    });

    $("#wizard-advanced-show").on("click", function (e) {
        show_step($(".wizard-advanced"));
        $(this).animate({'opacity': '0'}, 400);
        e.preventDefault();
        return true;
    });

});
