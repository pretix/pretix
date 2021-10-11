/*global $, Sortable*/
$(function () {
    $("[data-dnd-url]").each(function(){
        var container = $(this),
            url = container.data("dnd-url"),
            handle = $('<span class="btn btn-default btn-sm dnd-sort-handle"><i class="fa fa-arrows"></i></span>');

        container.find(".dnd-container").append(handle);
        if (container.find("[data-dnd-id]").length < 2) {
            handle.addClass("disabled");
            return;
        }

        Sortable.create(container.get(0), {
            filter: ".sortable-disabled",
            handle: ".dnd-sort-handle",
            onMove: function (evt) {
                return evt.related.className.indexOf('sortable-disabled') === -1;
            },
            onStart: function (evt) {
                container.addClass("sortable-dragarea");
                container.parent().addClass("sortable-sorting");
            },
            onEnd: function (evt) {
                container.removeClass("sortable-dragarea");
                container.parent().removeClass("sortable-sorting");

                var disabledUp = container.find(".sortable-up:disabled"),
                    firstUp = container.find(">tr[data-dnd-id] .sortable-up").first();
                if (disabledUp.length && disabledUp.get(0) !== firstUp.get(0)) {
                    disabledUp.prop("disabled", false);
                    firstUp.prop("disabled", true);
                }

                var disabledDown = container.find(".sortable-down:disabled"),
                    lastDown = container.find(">tr[data-dnd-id] .sortable-down").last();
                if (disabledDown.length && disabledDown.get(0) !== lastDown.get(0)) {
                    disabledDown.prop("disabled", false);
                    lastDown.prop("disabled", true);
                }
            },
            onSort: function (evt){
                var container = $(evt.to),
                    ids = container.find("[data-dnd-id]").toArray().map(function (e) { return e.dataset.dndId; });

                $.ajax(
                    {
                        'type': 'POST',
                        'url': url,
                        'headers': {'X-CSRFToken': $("input[name=csrfmiddlewaretoken]").val()},
                        'data': JSON.stringify({
                            ids: ids
                        }),
                        'contentType': "application/json",
                        'timeout': 30000
                    }
                );
            }
        });
    });
});
