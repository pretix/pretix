/*global $ */

$(function () {
    "use strict";

    var isOpera = Object.prototype.toString.call(window.opera) == '[object Opera]';

    $("details summary, details summary a").click(function (e) {
        var $details = $(this).closest("details");
        var isOpen = $details.prop("open");
        var $detailsNotSummary = $details.children(':not(summary)');
        if ($detailsNotSummary.is(':animated')) {
            e.preventDefault();
            return false;
        }
        if (isOpen) {
            $detailsNotSummary.stop().show().slideUp(500, function () {
                $details.prop("open", false);
            });
        } else {
            $detailsNotSummary.stop().hide();
            $details.prop("open", true);
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
        }
        $detailsSummary.attr({
            'role': 'button',
            'aria-controls': $details.attr('id')
        }).prop('tabIndex', 0).bind('selectstart dragstart mousedown', function () {
            return false;
        });
    });
});
