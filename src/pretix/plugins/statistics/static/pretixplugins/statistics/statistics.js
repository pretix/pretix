/*globals $, Morris, gettext*/
$(function () {
    $(".chart").css("height", "250px");
    new Morris.Area({
        element: 'obd_chart',
        data: JSON.parse($("#obd-data").html()),
        xkey: 'date',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Placed orders'), gettext('Paid orders')],
        lineColors: ['#000099', '#009900'],
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
        fillOpacity: 0.3,
        preUnits: $.trim($("#currency").html()) + ' '
    });
    new Morris.Bar({
        element: 'obp_chart',
        data: JSON.parse($("#obp-data").html()),
        xkey: 'item',
        ykeys: ['ordered', 'paid'],
        labels: [gettext('Placed orders'), gettext('Paid orders')],
        barColors: ['#000099', '#009900'],
        resize: true,
        xLabelAngle: 30
    });
});
