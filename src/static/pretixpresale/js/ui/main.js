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

    display_copy();
    // Copy answers
    $("#copy_answers").change(function() {
        if ($("#copy_answers:checked").length > 0) {
            bind_groups();
        } else {
            unbind_groups();
        }
    })
});

function display_copy() {
    var elements = $("input").filter(function(){
        return this.id.match(/^id_(\d+)/);
    });    
    var shouldElementBeVisible = (elements.length > 2);    
    $("#cp_copy").toggle(!!shouldElementBeVisible);   
}

function bind_groups() {
    
    var elements = $("input").filter(function(){
        return this.id.match(/^id_(\d+)/);
    });

    // first copy values
    for (var i=2; i<elements.length; i+=2) {
        if(elements[i])
            elements.eq(i).val(elements.eq(0).val());
        
        if(elements[i+1])
            elements.eq(i+1).val(parseInt(elements.eq(1).val(), 10));
    }

    // then bind fields
    elements.eq(0).keyup(function(){
        for (var i=2; i<elements.length; i+=2) {            
            elements.eq(i).val($(this).val());
        }        
    });

    elements.eq(1).keyup(function(){
        for (var i=2; i<elements.length; i+=2) {            
            elements.eq(i+1).val($(this).val());
        }
    });
    
    
}

function unbind_groups() {   
    var elements = $("input").filter(function(){
        return this.id.match(/^id_(\d+)/);
    });

    for(var i=0; i<elements.length; i++){
        elements.eq(i).unbind("keyup");
    }
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