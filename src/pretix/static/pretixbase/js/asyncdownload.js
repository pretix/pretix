/*global $, waitingDialog, gettext */
var async_dl_url = null;
var async_dl_timeout = null;

function async_dl_check() {
    "use strict";
    $.ajax(
        {
            'type': 'GET',
            'url': async_dl_url + '?ajax=1',
            'success': async_dl_check_callback,
            'error': async_dl_check_error,
            'context': this,
            'dataType': 'json'
        }
    );
}

function async_dl_check_callback(data, jqXHR, status) {
    "use strict";
    if (data.ready && data.redirect) {
        $("body").data('ajaxing', false);
        location.href = data.redirect;
        waitingDialog.hide();
        return;
    }
    async_dl_timeout = window.setTimeout(async_dl_check, 250);
    $("#loadingmodal p").text(gettext('Your request has been queued on the server and will now be ' +
                                      'processed. If this takes longer than two minutes, please contact us or go ' +
                                      'back in your browser and try again.'));
}

function async_dl_check_error(jqXHR, textStatus, errorThrown) {
    "use strict";
    $("body").data('ajaxing', false);
    waitingDialog.hide();
    var c = $(jqXHR.responseText).filter('.container');
    if (c.length > 0) {
        ajaxErrDialog.show(c.first().html());
    } else if (jqXHR.status >= 400) {
        alert(gettext('An error of type {code} occurred.').replace(/\{code\}/, jqXHR.status));
    }
}

$(function () {
    "use strict";
    $("body").on('click', 'a[data-asyncdownload]', function (e) {
        e.preventDefault();
        if ($("body").data('ajaxing')) {
            return;
        }
        async_dl_url = $(this).attr("href");
        $("body").data('ajaxing', true);
        waitingDialog.show(gettext('We are processing your request …'));
        $("#loadingmodal p").text(gettext('We are currently sending your request to the server. If this takes longer ' +
                                          'than one minute, please check your internet connection and then reload ' +
                                          'this page and try again.'));

        async_dl_check();
    });
});
