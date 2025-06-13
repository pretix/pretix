/*global $, Morris, gettext*/
$(function () {
    // Question view
    if (!$("#question_chart").length) {
        return;
    }

    $(".chart").css("height", "250px");
    var data_type = $("#question_chart").attr("data-type"),
        data = JSON.parse($("#question-chart-data").text() || "[]"),
        others_sum = 0,
        max_num = 8;

    data = data.map(function (d) {
        return {
            'value': d.count,
            'label': d.answer.length > 20 ? d.answer.substring(0, 20) + '…' : d.answer,
        }
    });

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
            others_sum += data[i].value;
        }
        data = data.slice(0, max_num);
        data.push({'value': others_sum, 'label': gettext('Others')});
    }

    if (data_type === 'B') {
        var colors;
        if (data[0].answer_bool) {
            colors = ['#50A167', '#C44F4F'];
        } else {
            colors = ['#C44F4F', '#50A167'];
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
            resize: true,
            colors: [
                '#7F4A91',
                '#50A167',
                '#FFB419',
                '#5F9CD4',
                '#C44F4F',
                '#83FFFA',
                '#FF6C38',
                '#1f5b8e',
                '#2d683c',
            ]
        });
    } else {  // M, N, S, T
        new Morris.Bar({
            element: 'question_chart',
            data: data,
            resize: true,
            xkey: 'label',
            ykeys: ['value'],
            labels: [gettext('Count')]
        });
    }

    // N, S, T
});

$(function () {
    // Question editor

    if (!$("#answer-options").length) {
        return;
    }

    // Question editor
    $("#id_type").change(question_page_toggle_view);
    $("#id_required").change(question_page_toggle_view);
    question_page_toggle_view();

    function question_page_toggle_view() {
        var show = $("#id_type").val() == "C" || $("#id_type").val() == "M";
        $("#answer-options").toggle(show);

        $("#valid-date").toggle($("#id_type").val() == "D");
        $("#valid-datetime").toggle($("#id_type").val() == "W");
        $("#valid-string").toggle($("#id_type").val() == "T" || $("#id_type").val() == "S");
        $("#valid-number").toggle($("#id_type").val() == "N");
        $("#valid-file").toggle($("#id_type").val() == "F");

        show = $("#id_type").val() == "B" && $("#id_required").prop("checked");
        $(".alert-required-boolean").toggle(show);
    }

    var $val = $("#id_dependency_values");
    var $dq = $("#id_dependency_question");
    var oldval = JSON.parse($("#dependency_value_val").text());
    function update_dependency_options() {
        $val.parent().find(".loading-indicator").remove();
        $("#id_dependency_values option").remove();
        $("#id_dependency_values").prop("required", false);

        var val = $dq.children("option:selected").val();
        if (!val) {
            $("#id_dependency_values").show();
            $val.show();
            return;
        }

        $("#id_dependency_values").prop("required", true);
        $val.hide();
        $val.parent().append("<div class=\"help-block loading-indicator\"><span class=\"fa" +
            " fa-cog fa-spin\"></span></div>");

        apiGET('/api/v1/organizers/' + $("body").attr("data-organizer") + '/events/' + $("body").attr("data-event") + '/questions/' + val + '/', function (data) {
            if (data.type === "B") {
                $val.append($("<option>").attr("value", "True").text(gettext("Yes")));
                $val.append($("<option>").attr("value", "False").text(gettext("No")));
            } else {
                for (var i = 0; i < data.options.length; i++) {
                    var opt = data.options[i];
                    var $opt = $("<option>").attr("value", opt.identifier).text(i18nToString(opt.answer));
                    $val.append($opt);
                }
            }
            if (oldval) {
                $val.val(oldval);
            }
            $val.parent().find(".loading-indicator").remove();
            $val.show();
        });
    }

    update_dependency_options();
    $dq.change(update_dependency_options);
});
