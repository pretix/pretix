/*global $, Sortable*/
$(function () {
    const allContainers = $("[data-dnd-url]");
    function updateAllSortButtonStates() {
        allContainers.each(function() { updateSortButtonState($(this)); });
    }
    function updateSortButtonState(container) {
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
    }

    let didSort = false, lastClick = 0;
    allContainers.each(function(){
        const container = $(this),
            url = container.data("dnd-url"),
            handle = $('<span class="btn btn-default btn-sm dnd-sort-handle"><i class="fa fa-arrows"></i></span>');

        container.find(".dnd-container").append(handle);
        if (!sessionStorage.dndShowMoveButtons) {
            container.find(".sortable-up, .sortable-down").addClass("sr-only").on("click", function () {
                sessionStorage.dndShowMoveButtons = 'true';
            });
        }
        if (container.find("[data-dnd-id]").length < 2 && !container.data("dnd-group")) {
            handle.addClass("disabled");
            return;
        }
        function maybeShowSortButtons() {
            if (Date.now() - lastClick < 3000) {
                $("[data-dnd-url] .sortable-up, [data-dnd-url] .sortable-down").removeClass("sr-only");
                updateAllSortButtonStates();
            }
            lastClick = Date.now();
        }
        container.find(".dnd-sort-handle").on("mouseup", maybeShowSortButtons);
        const group = container.data("dnd-group");
        const containers = group ? container.parent().find('[data-dnd-group="' + group + '"]') : container;
        Sortable.create(container.get(0), {
            filter: ".sortable-disabled",
            handle: ".dnd-sort-handle",
            group: group,
            onMove: function (evt) {
                return evt.related.className.indexOf('sortable-disabled') === -1;
            },
            onStart: function (evt) {
                containers.addClass("sortable-dragarea");
                container.parent().addClass("sortable-sorting");
                didSort = false;
            },
            onEnd: function (evt) {
                containers.removeClass("sortable-dragarea");
                container.parent().removeClass("sortable-sorting");
                if (!didSort) {
                    maybeShowSortButtons();
                } else {
                    $("[data-dnd-url] .sortable-up, [data-dnd-url] .sortable-down").addClass("sr-only");
                    delete sessionStorage.dndShowMoveButtons;
                }
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
