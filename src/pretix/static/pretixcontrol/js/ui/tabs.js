/*globals $*/

$(function () {
    var j = 0;
    $(".tabbed-form").each(function () {
        var $form = $(this);
        var $tabs = $("<ul>").addClass("nav nav-tabs").insertBefore($form);
        $form.addClass("tab-content");

        var i = 0;
        var preselect = null;
        $form.find("fieldset").each(function () {
            var $fieldset = $(this);
            var tid = "tab-" + j + "-" + i;
            var $tabli = $("<li>").appendTo($tabs);
            var $tablink = $("<a>").attr("role", "tab")
                .attr("data-toggle", "tab")
                .attr("href", "#" + tid)
                .text($fieldset.find("legend").text())
                .appendTo($tabli);
            if ($fieldset.find(".has-error, .alert-danger").length > 0) {
                $tablink.append(" ");
                $tablink.append($("<span>").addClass("fa fa-warning text-danger"));
                if (preselect === null) {
                    preselect = i;
                }
            }
            $fieldset.find("legend").remove();
            $fieldset.addClass("tab-pane").attr("id", tid);
            if (location.hash && ($fieldset.find(location.hash).length || location.hash === "#" + tid) && preselect === null) {
                preselect = i;
            }
            i++;
        });
        $tabs.find("a").get(preselect != null ? preselect : 0).click();
        $tabs.find("a").on('shown.bs.tab', function (e) {
            history.replaceState(null, null, e.target.getAttribute("href"));
        });
        j++;
    });
});
