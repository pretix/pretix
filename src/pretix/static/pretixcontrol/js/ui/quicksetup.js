$(function () {
    "use strict";

    var ticket_type_quota_calculation = function () {
        var sum = 0;
        $("#ticket-type-formset div[data-formset-form]").each(function () {
            if (!$(this).find("input[name$=DELETE]").prop("checked")) {
                var val = $(this).find("input[name$=quota]").val();
                if (val === "") {
                    sum = "∞";
                } else if (sum !== "∞") {
                    sum += parseInt(val);
                }
            }
        });
        $("#total-capacity").text(sum);
    };

    $("#ticket-type-formset").bind("formAdded", ticket_type_quota_calculation);
    $("#ticket-type-formset").on("change keyup keydown keypress", "input", function () {
        ticket_type_quota_calculation();
    });
    ticket_type_quota_calculation();

    $("#total-capacity-edit").click(function () {
        $("#id_total_quota").val(parseInt($("#total-capacity").text()));
        $("#total-capacity").hide();
        $("#id_total_quota").closest("div").removeClass("sr-only");
        $("#total-capacity-edit").hide();
    });
});
