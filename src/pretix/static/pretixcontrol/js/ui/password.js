/*global $,gettext,zxcvbn*/

$(function () {
    "use strict";

    $(".passwordcheck").each(function () {
        var $progress = $("<div>").addClass("progress password-progress"),
            $bar = $("<div>").addClass("progress-bar"),
            $input = $(this);
        $input.addClass("passwordcheck-with-progress");
        $progress.append($bar);
        $input.parent().append($progress);

        $input.bind("keyup change", function () {
            var user_data = ["pretix", "ticket"];
            var cls = "danger";

            $(".password-userinfo").each(function () {
                user_data = user_data.concat($(this).val().split(" "));
                user_data = user_data.concat($(this).val().split("@"));
            });
            var result = zxcvbn($input.val(), user_data);
            var percentage = Math.round((result.score + 1) / 5 * 100);

            if (result.score >= 3) {
                cls = "success";
            } else if (result.score === 2) {
                cls = "warning";
            }
            $bar.attr("class", "progress-bar progress-bar-" + cls + " progress-bar-" + percentage.toString());
       });
    });
});
