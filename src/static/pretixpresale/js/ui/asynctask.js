var async_task_id = null;
var async_task_timeout = null;
var async_task_check_url = null;

$(function () {
    $("body").on('submit', 'form[data-asynctask]', function (e) {
        e.preventDefault();
        if ($(this).data('ajaxing')) return;
        $(this).data('ajaxing', true);
        waitingDialog.show(default_loading_message);

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

function async_task_check() {
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
    if (data.ready && data.redirect) {
        location.href = data.redirect;
        return;
    }
    async_task_timeout = window.setTimeout(async_task_check, 500);
}

function async_task_callback(data, jqXHR, status) {
    $(this).data('ajaxing', false);
    if (data.redirect) {
        location.href = data.redirect;
        return;
    }
    async_task_id = data.async_id;
    async_task_check_url = data.check_url;
    async_task_timeout = window.setTimeout(async_task_check, 500);
}

function async_task_error(jqXHR, textStatus, errorThrown) {
    waitingDialog.hide();
    // TODO
    // if(jqXHR.status == 500) {
    // } if(jqXHR.status == 403) {
    // } if(jqXHR.status == 503) {
    // }
}
