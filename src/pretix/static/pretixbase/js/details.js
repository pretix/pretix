/*global $ */

setup_collapsible_details = function (el) {

    el.find('.sneak-peek-trigger').each(function() {
        var trigger = this;
        var button = this.querySelector('button');
        var content = document.getElementById(button.getAttribute('aria-controls'));
        if (content.scrollHeight < 200) {
            trigger.remove();
            content.classList.remove('sneak-peek-content');
            return;
        }
        content.setAttribute('aria-hidden', 'true');
        content.setAttribute('inert', true);
        button.setAttribute('aria-expanded', 'false');
        button.addEventListener('click', function (e) {
            button.setAttribute('aria-expanded', 'true');
            content.setAttribute('aria-hidden', 'false');
            content.removeAttribute('inert');

            content.addEventListener('transitionend', function() {
                content.classList.remove('sneak-peek-content');
                content.style.removeProperty('height');
                // we need to keep the trigger/button in the DOM to not irritate screenreaders toggling visibility
                trigger.classList.add('sr-only');
            }, {once: true});
            content.style.height = content.scrollHeight + 'px';

            button.addEventListener('click', function (e) {
                // this will be called by screenreader users if they kept focus on the button after expanding
                // we need to keep the trigger/button in the DOM to not irritate screenreaders toggling visibility
                var expanded = button.getAttribute('aria-expanded') == 'true';
                button.setAttribute('aria-expanded', !expanded);
                content.setAttribute('aria-hidden', expanded);
            });
            button.addEventListener('blur', function (e) {
                // if content is visible and the user leaves the button, we can safely remove the trigger/button
                if (button.getAttribute('aria-expanded') == 'true') {
                    trigger.remove();
                }
            });
        }, { once: true });

        var container = this.closest('details.sneak-peek-container');
        if (container) {
            function removeSneekPeakWhenClosed(e) {
                if (e.newState == "closed") {
                    container.removeEventListener("toggle", removeSneekPeakWhenClosed);
                    trigger.remove();
                    content.removeAttribute('aria-hidden');
                    content.removeAttribute('inert');
                    content.classList.remove('sneak-peek-content');
                }
            }
            container.addEventListener("toggle", removeSneekPeakWhenClosed);
        }
    });

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
        var $detailsNotSummary = $button.attr("aria-controls") ? $('#' + $button.attr("aria-controls")) : $(".variations", $details);
        var isOpen = !$detailsNotSummary.prop("hidden");
        if ($detailsNotSummary.is(':animated')) {
            e.preventDefault();
            return false;
        }

        var altLabel = $button.attr("data-label-alt");
        $button.attr("data-label-alt", $button.text().trim());
        $button.find("span").text(altLabel);
        $button.attr("aria-expanded", !isOpen);

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
