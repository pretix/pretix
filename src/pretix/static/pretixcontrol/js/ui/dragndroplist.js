/*global $, Sortable*/
$(function () {
    $("[data-dnd-url]").each(function(){
        var container = $(this),
            url = container.data("dnd-url"),
            handle = $('<span class="btn btn-default btn-sm dnd-sort-handle"><i class="fa fa-arrows"></i></span>');

        container.find(".dnd-container").append(handle);

        Sortable.create(container.get(0), {
            filter: ".sortable-disabled",
            handle: ".dnd-sort-handle",
            onMove: function (evt) {
                return evt.related.className.indexOf('sortable-disabled') === -1;
            },
            //ghostClass: "sortable-ghost",
            onStart: function (evt) {
                container.addClass("sortable-dragarea");
                container.parent().addClass("sortable-sorting");
            },
            onEnd: function (evt) {
                container.removeClass("sortable-dragarea");
                container.parent().removeClass("sortable-sorting");
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
