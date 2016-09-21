/*global $, gettext*/
var bankimport_transactionlist = {

    _btn_click: function (e) {
        console.log(e.delegateTarget);
        var trans_id = parseInt($(e.delegateTarget).attr("name").split("_")[1]);
        var value = $(e.delegateTarget).val();
        if (value === "discard") {
            bankimport_transactionlist.discard(trans_id);
        } else if (value === "accept") {
            bankimport_transactionlist.accept(trans_id);
        } else if (value === "retry") {
            bankimport_transactionlist.retry(trans_id);
        } else if (value === "assign") {
            bankimport_transactionlist.assign(trans_id);
        }
        return false;
    },

    _action: function (id, action, success) {
        $("tr[data-id=" + id + "] button").prop("disabled", true);
        var data = {
            "csrfmiddlewaretoken": $("[name=csrfmiddlewaretoken]").val()
        };
        data["action_" + id] = action;
        $.ajax({
            "method": "POST",
            "url": $(".transaction-list").attr("data-url"),
            "data": data,
            "dataType": "json",
            "success": function (data) {
                if (data.status == "ok") {
                    $("tr[data-id=" + id + "]").removeClass("has-error");
                    success();
                } else {
                    $("tr[data-id=" + id + "] button").prop("disabled", false);
                    $("tr[data-id=" + id + "] .help-block").remove();
                    $("tr[data-id=" + id + "]").addClass("has-error");
                    $("<p>").addClass("help-block").text(data.message).appendTo($("tr[data-id=" + id + "] td.actions"));
                }
            }
        });
    },

    discard: function (id) {
        bankimport_transactionlist._action(id, "discard", function () {
            $("tr[data-id=" + id + "] td").remove();
        });
    },

    retry: function (id) {
        bankimport_transactionlist._action(id, "retry", function () {
            $("tr[data-id=" + id + "] td.actions").html('').text(gettext("Marked as paid"));
        });
    },

    accept: function (id) {
        bankimport_transactionlist._action(id, "accept", function () {
            $("tr[data-id=" + id + "] td.actions").html('').text(gettext("Marked as paid"));
        });
    },

    assign: function (id) {
        bankimport_transactionlist._action(id, "assign:" + $("tr[data-id=" + id + "] input.form-control:not(.tt-hint)").val(), function () {
            $("tr[data-id=" + id + "] td.actions").html('').text(gettext("Marked as paid"));
        });
    },

    typeahead_source: function () {
        return new Bloodhound({
            datumTokenizer: Bloodhound.tokenizers.obj.whitespace('value'),
            queryTokenizer: Bloodhound.tokenizers.whitespace,
            remote: {
                url: $(".transaction-list").attr("data-url"),
                prepare: function (query, settings) {
                    settings.url = settings.url + '?query=' + encodeURIComponent(query);
                    return settings;
                },
                transform: function (object) {
                    var results = object.results;
                    var suggs = [];
                    var reslen = results.length;
                    for (var i = 0; i < reslen; i++) {
                        suggs.push(results[i]);
                    }
                    return suggs;
                }
            }
        });
    },

    init: function () {
        if ($(".transaction-list").length) {
            $(".transaction-list button").click(bankimport_transactionlist._btn_click);
            $(".transaction-list .form-control").typeahead(null, {
                minLength: 2,
                name: 'order-dataset',
                source: bankimport_transactionlist.typeahead_source(),
                display: function (obj) {
                    return obj.code;
                },
                templates: {
                    suggestion: function (obj) {
                        return '<div>' + obj.code + ' (' + obj.total + ', ' + obj.status + ')</div>';
                    }
                }
            }).keypress(function (e) {
                if (e.keyCode === 13) {
                    $(this).parent().parent().find("button[value=assign]").click();
                }
            });
        }

        if ($("[data-job-waiting]").length) {
            window.setTimeout(bankimport_transactionlist.check_state, 750);
        }
    },

    check_state: function () {
        $.getJSON($("[data-job-waiting-url]").attr("data-job-waiting-url"), function (data) {
            if (data.state == 'running' || data.state == 'pending') {
                window.setTimeout(bankimport_transactionlist.check_state, 750);
            } else {
                location.reload();
            }
        });
    }
};

$(function () {
    bankimport_transactionlist.init();
});
