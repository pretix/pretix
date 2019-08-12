/*global $,gettext*/

$(function () {
    if ($("div[data-lazy-id]").length == 0) {
        return;
    }
    $.getJSON("widgets.json", function (data) {
        $.each(data.widgets, function (k, v) {
            $("[data-lazy-id=" + v.lazy + "]").removeClass("widget-lazy-loading");
            $("[data-lazy-id=" + v.lazy + "] .widget").html(v.content);
        });
    });
});
