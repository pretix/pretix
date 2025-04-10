/*global $,u2f */
$(function () {
    $('.context-selector.dropdown').on('shown.bs.collapse shown.bs.dropdown', function () {
        $(this).parent().find("input").val("").trigger('forceRunQuery').focus();
    });
    $('.dropdown-menu .form-box input').click(function (e) {
        e.stopPropagation();
    });

    $("[data-event-typeahead]").each(function () {
        var $container = $(this);
        var $query = $(this).find('[data-typeahead-query]').length ? $(this).find('[data-typeahead-query]') : $($(this).attr("data-typeahead-field"));
        $container.find("li:not(.query-holder)").remove();
        var lastQuery = null;
        var runQueryTimeout = null;
        var loadIndicatorTimeout = null;
        var focusOutTimeout = null;
        function showLoadIndicator() {
            $container.find("li:not(.query-holder)").remove();
            $container.append("<li class='loading'><span class='fa fa-4x fa-cog fa-spin'></span></li>");
            $container.toggleClass('focused', $query.is(":focus") && $container.children().length > 0);
        }
        function runQuery() {
            var thisQuery = $query.val();
            if (thisQuery === lastQuery) return;
            lastQuery = $query.val();

            window.clearTimeout(loadIndicatorTimeout)
            loadIndicatorTimeout = window.setTimeout(showLoadIndicator, 80)

            $.getJSON(
                $container.attr("data-source") + "?query=" + encodeURIComponent($query.val()) + (typeof $container.attr("data-organizer") !== "undefined" ? "&organizer=" + $container.attr("data-organizer") : ""),
                function (data) {
                    if (thisQuery !== lastQuery) {
                        // Lost race condition
                        return;
                    }
                    window.clearTimeout(loadIndicatorTimeout);
                    $container.find("li:not(.query-holder)").remove();
                    $.each(data.results, function (i, res) {
                        let $linkContent = $("<div>");
                        if (res.type === "organizer") {
                            $linkContent.append(
                                $("<span>").addClass("event-name-full").append(
                                    $("<span>").addClass("fa fa-users fa-fw")
                                ).append(" ").append($("<div>").text(res.name).html())
                            )
                        } else if (res.type === "order" || res.type === "voucher") {
                            $linkContent.append(
                                $("<span>").addClass("event-name-full").append($("<div>").text(res.title).html())
                            ).append(
                                $("<span>").addClass("event-organizer").append(
                                    $("<span>").addClass("fa fa-calendar fa-fw")
                                ).append(" ").append($("<div>").text(res.event).html())
                            )
                        } else if (res.type === "user") {
                            $linkContent.append(
                                $("<span>").addClass("event-name-full").append(
                                    $("<span>").addClass("fa fa-user fa-fw")
                                ).append(" ").append($("<div>").text(res.name).html())
                            )
                        } else {
                            $linkContent.append(
                                $("<span>").addClass("event-name-full").append($("<div>").text(res.name).html())
                            ).append(
                                $("<span>").addClass("event-organizer").append(
                                    $("<span>").addClass("fa fa-users fa-fw")
                                ).append(" ").append($("<div>").text(res.organizer).html())
                            ).append(
                                $("<span>").addClass("event-daterange").append(
                                    $("<span>").addClass("fa fa-calendar fa-fw")
                                ).append(" ").append(res.date_range)
                            )
                        }

                        $container.append(
                            $("<li>").append(
                                $("<a>").attr("href", res.url).append(
                                    $linkContent
                                )
                            )
                        );
                    });
                    $container.toggleClass('focused', $query.is(":focus") && $container.children().length > 0);
                }
            );
        }
        $query.on("forceRunQuery", function () {
            runQuery();
        });
        $query.on("input", function () {
            if ($container.attr("data-typeahead-field") && $query.val() === "") {
                $container.removeClass('focused');
                $container.find("li:not(.query-holder)").remove();
                lastQuery = null;
                return;
            }
            window.clearTimeout(runQueryTimeout)
            runQueryTimeout = window.setTimeout(runQuery, 250)
        });
        $query.on("keydown", function (event) {
            var $selected = $container.find(".active");
            if (event.which === 13) {  // enter
                var $link = $selected.find("a");
                if ($link.length) {
                    location.href = $link.attr("href");
                }
                event.preventDefault();
                event.stopPropagation();
            }
        });
        $container.add($query).on("keydown", function (event) {
            if (event.which === 27) {  // escape
                $container.removeClass('focused');
            }
        }).on("focusin", function (event) {
            window.clearTimeout(focusOutTimeout);
            $(document.body).one("focusout", function (event) {
                focusOutTimeout = window.setTimeout(function () {
                    $container.removeClass('focused');
                }, 100);
            })
        });
        $query.on("keyup", function (event) {
            var $first = $container.find("li:not(.query-holder)").first();
            var $last = $container.find("li:not(.query-holder)").last();
            var $selected = $container.find(".active");

            if (event.which === 13) {  // enter
                event.preventDefault();
                event.stopPropagation();
                return true;
            } else if (event.which === 40) {  // down
                var $next;
                if ($selected.length === 0) {
                    $next = $first;
                } else {
                    $next = $selected.next();
                }
                if ($next.length === 0) {
                    $next = $first;
                }
                $selected.removeClass("active");
                $next.addClass("active");
                event.preventDefault();
                event.stopPropagation();
                return true;
            } else if (event.which === 38) {  // up
                if ($selected.length === 0) {
                    $selected = $first;
                }
                var $prev = $selected.prev();
                if ($prev.length === 0 || $prev.find("input").length > 0) {
                    $prev = $last;
                }
                $selected.removeClass("active");
                $prev.addClass("active");
                event.preventDefault();
                event.stopPropagation();
                return true;
            }
        });
    });
});
