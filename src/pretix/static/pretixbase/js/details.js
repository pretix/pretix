/*global $ */

setup_collapsible_details = function (el) {
    var isOpera = Object.prototype.toString.call(window.opera) == '[object Opera]';
    el.find("details summary, details summary a[data-toggle=variations]").click(function (e) {
        if (this.tagName !== "A" && $(e.target).closest("a").length > 0) {
            return true;
        }
        var $details = $(this).closest("details");
        var isOpen = $details.prop("open");
        var $detailsNotSummary = $details.children(':not(summary)');
        if ($detailsNotSummary.is(':animated')) {
            e.preventDefault();
            return false;
        }
        if (isOpen) {
            $details.removeClass("details-open");
            $detailsNotSummary.stop().show().slideUp(500, function () {
                $details.prop("open", false);
            });
        } else {
            $detailsNotSummary.stop().hide();
            $details.prop("open", true);
            $details.addClass("details-open");
            $detailsNotSummary.slideDown();
        }
        e.preventDefault();
        return false;
    }).keyup(function (event) {
        if (32 == event.keyCode || (13 == event.keyCode && !isOpera)) {
            // Space or Enter is pressed — trigger the `click` event on the `summary` element
            // Opera already seems to trigger the `click` event when Enter is pressed
            event.preventDefault();
            $(this).click();
        }
    });

    $('details').each(function () {
        var $details = $(this),
            $detailsSummary = $('summary', $details).first(),
            $detailsNotSummary = $details.children(':not(summary)');
        $details.prop('open', typeof $details.attr('open') == 'string');
        if (!$details.prop('open')) {
            $detailsNotSummary.hide();
        } else {
            $details.addClass("details-open");
        }
        $detailsSummary.attr({
            'role': 'button',
            'aria-controls': $details.attr('id')
        }).prop('tabIndex', 0).bind('selectstart dragstart mousedown', function () {
            return false;
        });
    });
};

$(function () {
    "use strict";

    setup_collapsible_details($("body"));
});
