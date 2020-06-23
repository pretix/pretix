/*global $, Sortable*/
$(function () {
    $("[data-dnd-url]").each(function(){
        var container = $(this),
            url = container.data("dnd-url"),
            handle = $('<span class="btn btn-default btn-sm dnd-sort-handle"><i class="fa fa-arrows"></i></span>');

        console.log(container, container.find(".dnd-container"));
        container.find(".dnd-container").append(handle);

        Sortable.create(container.get(0), {
            handle: ".dnd-sort-handle",
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
