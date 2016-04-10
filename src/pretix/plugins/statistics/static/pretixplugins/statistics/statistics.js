/*globals $, Morris*/
$(function () {
    new Morris.Area({
        element: 'obd_chart',
        data: JSON.parse($("#obd-data").html()),
        xkey: 'date',
        ykeys: ['ordered', 'paid'],
        labels: ['{% trans "Placed orders" %}', '{% trans "Paid orders" %}'],
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
        labels: ['{% trans "Total revenue" %}'],
        smooth: false,
        resize: true,
        fillOpacity: 0.3,
        preUnits: '{{ request.event.currency }} '
    });
    new Morris.Bar({
        element: 'obp_chart',
        data: JSON.parse($("#odp-data").html()),
        xkey: 'item',
        ykeys: ['ordered', 'paid'],
        labels: ['{% trans "Placed orders" %}', '{% trans "Paid orders" %}'],
        barColors: ['#000099', '#009900'],
        resize: true
    });
});