function preview_task_callback(data, jqXHR, status) {
    "use strict";
    if (data.item){
        $('#' + data.item).data('ajaxing', false);
        for (var m in data.msgs){
            var target = $('textarea[preview-for=' + m + ']');
            if (target.length === 1){
                target.text(data.msgs[m]);
            }
        }
    }
}

function preview_task_error(item) {
    "use strict";
    return function(jqXHR, textStatus, errorThrown) {
        $('#' + item).data('ajaxing', false);
        $('#' + itemName + '_preview textarea').text(gettext('An error occurred.'));
        if (textStatus === "timeout") {
            alert(gettext("The request took to long. Please try again."));
        } else {
            if (jqXHR.status >= 400 && jqXHR.status < 500) {
                alert(gettext('An error of type {code} occurred.').replace(/\{code\}/, jqXHR.status));
            } else {
                alert(gettext('We currently cannot reach the server. Please try again. ' +
                              'Error code: {code}').replace(/\{code\}/, jqXHR.status));
            }
        }
    }
}

$(function () {
    "use strict";

    $('a[type=preview]').each(function () {
        $(this).attr("href", "#" + $(this).closest('.preview-panel').attr('id') + "_preview");
    });

    $('a[type=edit]').each(function () {
        $(this).attr("href", "#" + $(this).closest('.preview-panel').attr('id') + "_edit");
    });

    $('.preview-panel').each(function () {
        var pid = $(this).attr('id');
        $(this).find('#' + pid + '_preview textarea').each( function () {
            $(this).attr('preview-for', $(this).attr('name'))
                    .removeAttr('id').removeAttr('name').prop('disabled', true);
        });
    });

    $('a[type=preview]').on('click', function () {
        var itemName = $(this).closest('.preview-panel').attr('id');
        if ($('#' + itemName).data('ajaxing') || $(this).parent('.active').length !== 0) {
            return;
        }

        // gathering data
        var parentForm = $(this).closest('form');
        var previewUrl = $(parentForm).attr('mail-preview-url');
        var token = $(parentForm).find('input[name=csrfmiddlewaretoken]').val();
        var dataString = 'item=' + itemName + '&csrfmiddlewaretoken=' + token + '&ajax=1';
        $('#' + itemName + '_edit textarea').each(function () {
            dataString += $(this).serialize();
        });

        // prepare for ajax
        $('#' + itemName).data('ajaxing', true);
        $('#' + itemName + '_preview textarea').text(gettext('Generating messages …'));

        $.ajax(
            {
                'type': 'POST',
                'url': previewUrl,
                'data': dataString,
                'success': preview_task_callback,
                'error': preview_task_error(itemName),
                'dataType': 'json',
                'timeout': 60000,
            }
        );

    });
});