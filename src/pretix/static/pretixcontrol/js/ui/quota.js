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
            '#3b1c4a', // paid
            '#7f4a91', // pending
            '#d36060', // vouchers
            '#ffb419', // carts
            '#5f9cd4', // waiting list
            '#50a167' // available
        ]
    });
});
