function preview_task_callback(data, jqXHR, status) {
    "use strict";
    if (data.item) {
        $('#' + data.item + '_panel').data('ajaxing', false);
        for (var m in data.msgs){
            var target = $('div[for=' + data.item + '][lang=' + m +']');
            if (target.length === 1){
                target.html(data.msgs[m]);
                target.find('.placeholder').tooltip();
            }
        }
    }
}

function preview_task_error(item) {
    "use strict";
    return function(jqXHR, textStatus, errorThrown) {
        $('#' + item + '_panel').data('ajaxing', false);
        $('#' + item + '_preview div').text(gettext('An error has occurred.'));
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

    $('.mail-preview .placeholder').tooltip();
    $('a[type=preview]').on('click', function () {
        var itemName = $(this).closest('.preview-panel').attr('for');
        if ($('#' + itemName + '_panel').data('ajaxing') || $(this).parent('.active').length !== 0) {
            return;
        }

        // gathering data
        var parentForm = $(this).closest('form');
        var previewUrl = $(parentForm).attr('mail-preview-url');
        var token = $(parentForm).find('input[name=csrfmiddlewaretoken]').val();
        var dataString = 'item=' + itemName + '&csrfmiddlewaretoken=' + token;
        $('#' + itemName + '_edit textarea').each(function () {
            dataString += '&' + $(this).serialize();
        });

        // prepare for ajax
        $('#' + itemName + '_panel').data('ajaxing', true);
        $('#' + itemName + '_preview div').text(gettext('Generating messages …'));

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
