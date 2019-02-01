/*globals $, Morris, gettext, django*/
function gettext(msgid) {
    if (typeof django !== 'undefined' && typeof django.gettext !== 'undefined') {
        return django.gettext(msgid);
    }
    return msgid;
}
$(function () {
    $(".chart").css("height", "250px");
    new Morris.Area({
        element: 'obd_chart',
        data: JSON.parse($("#obd-data").html()),
        xkey: 'date',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Placed orders'), gettext('Paid orders')],
        lineColors: ['#3b1c4a', '#50a167'],
        smooth: false,
        resize: true,
        fillOpacity: 0.3,
        behaveLikeLine: true
    });
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
    new Morris.Bar({
        element: 'obp_chart',
        data: JSON.parse($("#obp-data").html()),
        xkey: 'item_short',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Placed orders'), gettext('Paid orders')],
        barColors: ['#3b1c4a', '#50a167'],
        hoverCallback: function (index, options, content, row) {
            console.log(content);
            var $c = $("<div>" + content + "</div>");
            var $label = $c.find(".morris-hover-row-label");
            $label.text(row.item);
            var newc = $label.get(0).outerHTML;
            $c.find('.morris-hover-point').each(function (i, r) {
                if ($.trim($(r).text().split("\n")[2]) !== "0") {
                    newc += r.outerHTML;
                }
            });
            return newc;
        },
        resize: true,
        xLabelAngle: 30
    });
});
