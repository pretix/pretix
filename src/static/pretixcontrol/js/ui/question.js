/*global $, Morris, gettext*/
$(function () {
    if (!$("#question-stats").length) {
        return;
    }

    $(".chart").css("height", "250px");
    var data_type = $("#question_chart").attr("data-type"),
        data = JSON.parse($("#question-chart-data").html()),
        others_sum = 0,
        max_num = 8;

    for (var i in data) {
        data[i].value = data[i].count;
        data[i].label = data[i].answer;
        if (data[i].label.length > 20) {
            data[i].label = data[i].label.substring(0, 20) + '…';
        }
    }

    if (data_type == 'N') {
        // Sort
        data.sort(function (a, b) {
            if (parseFloat(a.label) > parseFloat(b.label)) {
                return 1;
            } else if (parseFloat(a.label) < parseFloat(b.label)) {
                return -1;
            } else {
                return 0;
            }
        });
        max_num = 20;
    }

    // Limit shown options
    if (data.length > max_num) {
        for (var i = max_num; i < data.length; i++) {
            others_sum += data[i].count;
        }
        data = data.slice(0, max_num);
        data.push({'value': others_sum, 'label': gettext('Others')});
    }

    if (data_type === 'B') {
        var colors;
        if (data[0].answer_bool) {
            colors = ['#41A351', '#BD362F'];
        } else {
            colors = ['#BD362F', '#41A351'];
        }
        new Morris.Donut({
            element: 'question_chart',
            data: data,
            resize: true,
            colors: colors
        });
    } else if (data_type === 'C') {
        new Morris.Donut({
            element: 'question_chart',
            data: data,
            resize: true
        });
    } else {  // M, N, S, T
        new Morris.Bar({
            element: 'question_chart',
            data: data,
            resize: true,
            xkey: 'label',
            ykeys: ['count'],
            labels: [gettext('Count')]
        });
    }

    // N, S, T
});
