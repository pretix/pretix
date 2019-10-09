/*global $, Sortable*/
$(function () {
    $("[data-dnd-url]").each(function(){
        var container = $(this),
            url = container.data("dnd-url"),
            up = container.find("a:has(.fa-arrow-up)"),
            handle = $('<span class="btn btn-default btn-sm dnd-sort-handle"><i class="fa fa-arrows"></i></span>');

        function hideArrows(container){
            var up = container.find("a:has(.fa-arrow-up)"),
                firstUp = up.first(),
                down = container.find("a:has(.fa-arrow-down)"),
                lastDown = down.last();
            up.not(firstUp).css("display","none");
            down.not(lastDown).css("display","none");
            firstUp.css("display","inline-block");
            lastDown.css("display","inline-block");
        }
        up.after(handle);
        hideArrows(container);

        Sortable.create(container.get(0), {
            handle: ".dnd-sort-handle",
            onSort: function(evt){
                var container = $(evt.to),
                    ids = container.find("[data-dnd-id]").toArray().map(e => e.dataset.dndId);

                hideArrows(container);

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
