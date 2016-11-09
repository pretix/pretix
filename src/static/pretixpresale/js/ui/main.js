/*global $ */

$(function () {
    "use strict";
    $("input[data-toggle=radiocollapse]").change(function () {
        $($(this).attr("data-parent")).find(".collapse.in").collapse('hide');
        $($(this).attr("data-target")).collapse('show');
    });
    $(".js-only").removeClass("js-only");
    $(".variations").hide();
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

    $("#ajaxerr").on("click", ".ajaxerr-close", ajaxErrDialog.hide);
    
    // Copy answers
    $(".js-copy-answers").click(function (e) {
        e.preventDefault();
        var idx = $(this).data('id');
        bind_groups(idx);
    });
});

function bind_groups(idx) {    
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

var waitingDialog = {
    show: function (message) {
        "use strict";
        $("#loadingmodal").find("h1").html(message);
        $("body").addClass("loading");
    },
    hide: function () {
        "use strict";
        $("body").removeClass("loading");
    }
};

var ajaxErrDialog = {
    show: function (c) {
        "use strict";
        $("#ajaxerr").html(c);
        $("#ajaxerr .links").html("<a class='btn btn-default ajaxerr-close'>"
                                  + gettext("Close message") + "</a>");
        $("body").addClass("ajaxerr");
    },
    hide: function () {
        "use strict";
        $("body").removeClass("ajaxerr");
    }
};