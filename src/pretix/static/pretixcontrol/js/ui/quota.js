/*globals $, Morris, gettext*/
$(function () {
    if (!$("#quota-stats").length) {
        return;
    }

    $(".chart").css("height", "250px");
    new Morris.Donut({
        element: 'quota_chart',
        data: JSON.parse($("#quota-chart-data").html()),
        resize: true,
        colors: [
            '#0044CC', // paid
            '#0088CC', // pending
            '#BD362F', // vouchers
            '#F89406', // carts
            '#51A351' // available
        ]
    });
});
