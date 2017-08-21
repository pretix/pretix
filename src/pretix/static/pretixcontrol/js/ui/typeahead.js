/*global $,u2f */
$(function () {
    $('ul.navbar-nav .dropdown, .navbar-events-collapse').on('shown.bs.collapse shown.bs.dropdown', function () {
        $(this).parent().find("input").val("").change().focus();
    });
    $('.dropdown-menu .form-box input').click(function (e) {
        e.stopPropagation();
    });

    $("[data-event-typeahead]").each(function () {
        var $container = $(this);
        var $query = $(this).find('[data-typeahead-query]');
        $query.closest("li").nextAll().remove();

        $query.on("change", function () {
            $.getJSON(
                $container.attr("data-source") + "?query=" + encodeURIComponent($query.val()),
                function (data) {
                    $query.closest("li").nextAll().remove();
                    $.each(data.results, function (i, res) {
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
                                )
                            )
                        );
                    });
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
        $query.on("keyup", function (event) {
            var $first = $query.closest("li").next();
            var $last = $query.closest("li").nextAll().last();
            var $selected = $container.find(".active");

            if (event.which === 13) {  // enter
                event.preventDefault();
                event.stopPropagation();
                return true;
            } else if (event.which === 40) {  // down
                if ($selected.length === 0) {
                    $selected = $query.closest("li");
                }
                var $next = $selected.next();
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
                    $selected = $container.first();
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
