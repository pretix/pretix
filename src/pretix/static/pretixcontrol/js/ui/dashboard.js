/*global $,gettext*/

$(function () {
    if ($("div[data-lazy-id]").length == 0) {
        return;
    }
    $.getJSON("widgets.json" + ($("select[name='subevent']").val() ? "?subevent=" + $("select[name='subevent']").val() : ""), function (data) {
        $.each(data.widgets, function (k, v) {
            $("[data-lazy-id=" + v.lazy + "]").removeClass("widget-lazy-loading");
            $("[data-lazy-id=" + v.lazy + "] .widget").html(v.content);
        });
    });
});
$(function () {
    if ($("#logs_target").length == 0) {
        return;
    }
    $.get("logs/embed", function (data) {
        $("#logs_target").html(data)
        add_log_expand_handlers($("#logs_target"))
    });
});

function gettext(msgid) {
    if (typeof django !== 'undefined' && typeof django.gettext !== 'undefined') {
        return django.gettext(msgid);
    }
    return msgid;
}

$(function () {
    $(".chart").css("height", "250px");
    new Morris.Area({
        element: 'rev_chart',
        data: JSON.parse($("#rev-data").html()),
        xkey: 'date',
        ykeys: ['revenue'],
        labels: [gettext('Total revenue')],
        smooth: false,
        resize: true,
        lineColors: ['#3b1c4a'],
        fillOpacity: 0.3,
        preUnits: $.trim($("#currency").html()) + ' '
    });
});
