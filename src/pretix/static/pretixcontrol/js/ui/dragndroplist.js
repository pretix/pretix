/*global $, Sortable*/
$(function () {
    $("[data-dnd-url]").each(function(){
        var container = $(this),
            url = container.data("dnd-url"),
            handle = $("<span>", {class: "btn btn-default btn-sm dnd-sort-handle"});
        handle.append('<i class="fa fa-arrows"></i>');
        container.find("a:has(.fa-arrow-up)").remove();
        container.find("a:has(.fa-arrow-down)").replaceWith(handle);

        Sortable.create(container.get(0), {
            handle: ".dnd-sort-handle",
            onSort: function(evt){
                var ids = $(evt.to).find("[data-dnd-id]").toArray().map(e => e.dataset.dndId);
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
