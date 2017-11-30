/*globals $, Morris, gettext*/
$(function () {
    if (!$("div[data-formset-prefix=checkinlist_set]").length) {
        return;
    }

    var $namef = $("input[id^=id_name]").first();
    var lastValue = $namef.val();
    $namef.change(function () {
        var field = $("div[data-formset-prefix=checkinlist_set] input[id$=name]").first();
        if (field.val() === lastValue) {
            lastValue = $(this).val();
            field.val(lastValue);
        }
    });

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
