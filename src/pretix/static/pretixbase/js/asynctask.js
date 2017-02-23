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
            'error': async_task_check_error,
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
    $("#loadingmodal p").text(gettext('Your request has been queued on the server and will now be ' +
                                      'processed. If this takes longer than two minutes, please contact us or go ' +
                                      'back in your browser and try again.'));
}

function async_task_check_error(jqXHR, textStatus, errorThrown) {
    "use strict";
    var c = $(jqXHR.responseText).filter('.container');
    if (c.length > 0) {
        $("body").data('ajaxing', false);
        waitingDialog.hide();
        ajaxErrDialog.show(c.first().html());
    } else {
        if (jqXHR.status >= 400 && jqXHR.status < 500) {
            $("body").data('ajaxing', false);
            waitingDialog.hide();
            alert(gettext('An error of type {code} occured.').replace(/\{code\}/, jqXHR.status));
        } else {
            // 500 can be an application error or overload in some cases :(
            $("#loadingmodal p").text(gettext('We currenctly cannot reach the server, but we keep trying.' +
                                              ' Last error code: {code}').replace(/\{code\}/, jqXHR.status));
            async_task_timeout = window.setTimeout(async_task_check, 5000);
        }
    }
}

function async_task_callback(data, jqXHR, status) {
    "use strict";
    $("body").data('ajaxing', false);
    if (data.redirect) {
        location.href = data.redirect;
        return;
    }
    async_task_id = data.async_id;
    async_task_check_url = data.check_url;
    async_task_timeout = window.setTimeout(async_task_check, 100);

    $("#loadingmodal p").text(gettext('Your request has been queued on the server and will now be ' +
                                      'processed. If this takes longer than two minutes, please contact us or go ' +
                                      'back in your browser and try again.'));
    if (location.href.indexOf("async_id") === -1) {
        history.pushState({}, "Waiting", async_task_check_url.replace(/ajax=1/, ''));
    }
}

function async_task_error(jqXHR, textStatus, errorThrown) {
    "use strict";
    $("body").data('ajaxing', false);
    if (textStatus === "timeout") {
        alert(gettext("The request took to long. Please try again."));
        waitingDialog.hide();
    } else if (jqXHR.responseText.indexOf('container') > 0) {
        var c = $(jqXHR.responseText).filter('.container');
        waitingDialog.hide();
        ajaxErrDialog.show(c.first().html());
    } else {
        if (jqXHR.status >= 400 && jqXHR.status < 500) {
            waitingDialog.hide();
            alert(gettext('An error of type {code} occured.').replace(/\{code\}/, jqXHR.status));
        } else {
            waitingDialog.hide();
            alert(gettext('We currenctly cannot reach the server. Please try again. ' +
                          'Error code: {code}').replace(/\{code\}/, jqXHR.status));
        }
    }
}

$(function () {
    "use strict";
    $("body").on('submit', 'form[data-asynctask]', function (e) {
        e.preventDefault();
        if ($("body").data('ajaxing')) {
            return;
        }
        async_task_id = null;
        $("body").data('ajaxing', true);
        waitingDialog.show(gettext('We are processing your request …'));
        $("#loadingmodal p").text(gettext('We are currently sending your request to the server. If this takes longer ' +
                                          'than one minute, please check your internet connection and then reload ' +
                                          'this page and try again.'));

        $.ajax(
            {
                'type': 'POST',
                'url': $(this).attr('action'),
                'data': $(this).serialize() + '&ajax=1',
                'success': async_task_callback,
                'error': async_task_error,
                'context': this,
                'dataType': 'json',
                'timeout': 60000,
            }
        );
    });
});

var waitingDialog = {
    show: function (message) {
        "use strict";
        $("#loadingmodal").find("h1").html(message);
        $("body").addClass("loading");
    },
    hide: function () {
        "use strict";
        $("body").removeClass("loading");
    }
};

var ajaxErrDialog = {
    show: function (c) {
        "use strict";
        $("#ajaxerr").html(c);
        $("#ajaxerr .links").html("<a class='btn btn-default ajaxerr-close'>"
                                  + gettext("Close message") + "</a>");
        $("body").addClass("ajaxerr");
    },
    hide: function () {
        "use strict";
        $("body").removeClass("ajaxerr");
    }
};
