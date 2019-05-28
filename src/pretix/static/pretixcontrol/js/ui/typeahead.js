/*global $,u2f */
$(function () {
    $('.sidebar .dropdown, ul.navbar-nav .dropdown, .navbar-events-collapse').on('shown.bs.collapse shown.bs.dropdown', function () {
        $(this).parent().find("input").val("").change().focus();
    });
    $('.dropdown-menu .form-box input').click(function (e) {
        e.stopPropagation();
    });

    $("[data-event-typeahead]").each(function () {
        var $container = $(this);
        var $query = $(this).find('[data-typeahead-query]').length ? $(this).find('[data-typeahead-query]') : $($(this).attr("data-typeahead-field"));
        $container.find("li:not(.query-holder)").remove();

        $query.on("change", function () {
            if ($container.attr("data-typeahead-field") && $query.val() === "") {
                $container.removeClass('focused');
                $container.find("li:not(.query-holder)").remove();
                return;
            }
            $.getJSON(
                $container.attr("data-source") + "?query=" + encodeURIComponent($query.val()) + (typeof $container.attr("data-organizer") !== "undefined" ? "&organizer=" + $container.attr("data-organizer") : ""),
                function (data) {
                    $container.find("li:not(.query-holder)").remove();
                    $.each(data.results, function (i, res) {
                        if (res.type === "organizer") {
                            $container.append(
                                $("<li>").append(
                                    $("<a>").attr("href", res.url).append(
                                        $("<div>").append(
                                            $("<span>").addClass("event-name-full").append(
                                                $("<span>").addClass("fa fa-users fa-fw")
                                            ).append(" ").append($("<div>").text(res.name).html())
                                        )
                                    ).on("mousedown", function (event) {
                                        if ($(this).length) {
                                            location.href = $(this).attr("href");
                                        }
                                        $(this).parent().addClass("active");
                                        event.preventDefault();
                                        event.stopPropagation();
                                    })
                                )
                            );
                        } else if (res.type === "user") {
                            $container.append(
                                $("<li>").append(
                                    $("<a>").attr("href", res.url).append(
                                        $("<div>").append(
                                            $("<span>").addClass("event-name-full").append(
                                                $("<span>").addClass("fa fa-user fa-fw")
                                            ).append(" ").append($("<div>").text(res.name).html())
                                        )
                                    ).on("mousedown", function (event) {
                                        if ($(this).length) {
                                            location.href = $(this).attr("href");
                                        }
                                        $(this).parent().addClass("active");
                                        event.preventDefault();
                                        event.stopPropagation();
                                    })
                                )
                            );
                        } else {
                            $container.append(
                                $("<li>").append(
                                    $("<a>").attr("href", res.url).append(
                                        $("<div>").append(
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
                                    ).on("mousedown", function (event) {
                                        if ($(this).length) {
                                            location.href = $(this).attr("href");
                                        }
                                        $(this).parent().addClass("active");
                                        event.preventDefault();
                                        event.stopPropagation();
                                    })
                                )
                            );
                        }
                    });
                    $container.toggleClass('focused', $query.is(":focus") && $container.children().length > 0);
                }
            );
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
        $query.on("blur", function (event) {
            $container.removeClass('focused');
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
            } else {
                $(this).change();
            }
        });
    });
});
