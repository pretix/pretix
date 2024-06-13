/*global $, Sortable*/
$(function () {
    $("[data-dnd-url]").each(function(){
        const container = $(this),
            url = container.data("dnd-url"),
            handle = $('<span class="btn btn-default btn-sm dnd-sort-handle"><i class="fa fa-arrows"></i></span>');

        container.find(".dnd-container").append(handle);
        container.find(".sortable-up, .sortable-down").addClass("sr-only");
        if (container.find("[data-dnd-id]").length < 2 && !container.data("dnd-group")) {
            handle.addClass("disabled");
            return;
        }
        let didSort = false, lastClick = 0;
        function handleMouseUp() {
            if (Date.now() - lastClick < 6000) {
                container.find(".sortable-up, .sortable-down").removeClass("sr-only");
            }
            lastClick = Date.now();
        }
        container.find(".dnd-sort-handle").on("mouseup", handleMouseUp);
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
                didSort = false;
            },
            onEnd: function (evt) {
                container.removeClass("sortable-dragarea");
                container.parent().removeClass("sortable-sorting");
                if (!didSort) handleMouseUp();
            },
            onSort: function (evt){
                if (evt.target !== evt.to) return;
                didSort = true;

                const ids = container.find("[data-dnd-id]").toArray().map(function (e) { return e.dataset.dndId; });
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
