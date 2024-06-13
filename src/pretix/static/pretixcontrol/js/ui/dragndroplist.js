/*global $, Sortable*/
$(function () {
    $("[data-dnd-url]").each(function(){
        var container = $(this),
            url = container.data("dnd-url"),
            handle = $('<span class="btn btn-default btn-sm dnd-sort-handle"><i class="fa fa-arrows"></i></span>');

        container.find(".dnd-container").append(handle);
        container.find(".sortable-up, .sortable-down").addClass("sr-only");
        if (container.find("[data-dnd-id]").length < 2 && !container.data("dnd-group")) {
            handle.addClass("disabled");
            return;
        }

        Sortable.create(container.get(0), {
            filter: ".sortable-disabled",
            handle: ".dnd-sort-handle",
            group: container.data("dnd-group"),
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
            },
            onSort: function (evt){
                if (evt.target !== evt.to) return;

                var ids = container.find("[data-dnd-id]").toArray().map(function (e) { return e.dataset.dndId; });

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
