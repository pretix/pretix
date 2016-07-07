/*global $, waitingDialog, gettext */
var async_task_id = null;
var async_task_timeout = null;
var async_task_check_url = null;

function async_task_check() {
    "use strict";
    $.ajax(
        {
            'type': 'GET',
            'url': async_task_check_url,
            'success': async_task_check_callback,
            'error': async_task_error,
            'context': this,
            'dataType': 'json'
        }
    );
}

function async_task_check_callback(data, jqXHR, status) {
    "use strict";
    if (data.ready && data.redirect) {
        location.href = data.redirect;
        return;
    }
    async_task_timeout = window.setTimeout(async_task_check, 250);
}

function async_task_callback(data, jqXHR, status) {
    "use strict";
    $(this).data('ajaxing', false);
    if (data.redirect) {
        location.href = data.redirect;
        return;
    }
    async_task_id = data.async_id;
    async_task_check_url = data.check_url;
    async_task_timeout = window.setTimeout(async_task_check, 100);
}

function async_task_error(jqXHR, textStatus, errorThrown) {
    "use strict";
    waitingDialog.hide();
    // TODO: Handle status codes != 200
    var c = $(jqXHR.responseText).filter('.container');
    if (c.length > 0) {
        ajaxErrDialog.show(c.first().html());
    } else {
        alert(gettext('Unknown error.'));
    }
}

$(function () {
    "use strict";
    $("body").on('submit', 'form[data-asynctask]', function (e) {
        e.preventDefault();
        if ($(this).data('ajaxing')) {
            return;
        }
        $(this).data('ajaxing', true);
        waitingDialog.show(gettext('We are processing your request…'));

        $.ajax(
            {
                'type': 'POST',
                'url': $(this).attr('action'),
                'data': $(this).serialize() + '&ajax=1',
                'success': async_task_callback,
                'error': async_task_error,
                'context': this,
                'dataType': 'json'
            }
        );
    });
});
