/*global $ */

setup_collapsible_details = function (el) {
    var isOpera = Object.prototype.toString.call(window.opera) == '[object Opera]';
    el.find("details summary").click(function (e) {
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
            if ($details.find(".has-error, .alert-danger").length) {
                $details.addClass("details-open");
                $details.prop('open', true);
            } else {
                $detailsNotSummary.hide();
            }
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

    el.find("article button[data-toggle=variations]").click(function (e) {
        var $button = $(this);
        var $details = $button.closest("article");
        var $detailsNotSummary = $(".variations", $details);
        var isOpen = !$detailsNotSummary.prop("hidden");
        if ($detailsNotSummary.is(':animated')) {
            e.preventDefault();
            return false;
        }

        var altLabel = $button.attr("data-label-alt");
        $button.attr("data-label-alt", $button.text());
        $button.text(altLabel);
        altLabel = $button.attr("data-aria-label-alt");
        $button.attr("data-aria-label-alt", $button.attr("aria-label"));
        $button.attr("aria-label", altLabel);

        if (isOpen) {
            $details.removeClass("details-open");
            $detailsNotSummary.stop().show().slideUp(500, function () {
                $detailsNotSummary.prop("hidden", true);
            });
        } else {
            $detailsNotSummary.prop("hidden", false).stop().hide();
            $details.addClass("details-open");
            $detailsNotSummary.slideDown();
        }
        e.preventDefault();
        return false;
    });
    el.find(".variations-collapsed").prop("hidden", true);
};

$(function () {
    "use strict";

    setup_collapsible_details($("body"));
});
