/*global $,gettext*/

$(function () {
    if ($("div[data-lazy-id]").length == 0) {
        return;
    }
    $.getJSON("widgets.json" + ($("select[name='subevent']").val() ? "?subevent=" + $("select[name='subevent']").val() : ""), function (data) {
        $.each(data.widgets, function (k, v) {
            $("[data-lazy-id=" + v.lazy + "]").removeClass("widget-lazy-loading");
            $("[data-lazy-id=" + v.lazy + "] .widget").html(v.content);
        });
    });
});
$(function () {
    if ($("#logs_target").length == 0) {
        return;
    }
	$.get("dashboard/partials/logs", function (data) {
		$("#logs_target").html(data)
		add_log_expand_handlers($("#logs_target"))
	});
    $.get("dashboard/partials/warnings", function (data) {
				$("#warnings_loading").remove()
        $("#warnings_target").html(data)
    });
});
