/*global $, waitingDialog, gettext */
var async_task_id = null;
var async_task_timeout = null;
var async_task_check_url = null;
var async_task_old_url = null;
var async_task_is_download = false;
var async_task_is_long = false;
var async_task_dont_redirect = false;

var async_task_status_messages = {
    long_task_started: gettext(
        'Your request is currently being processed. Depending on the size of your event, this might take up to ' +
        'a few minutes.'
    ),
    long_task_pending: gettext(
        'Your request has been queued on the server and will soon be ' +
        'processed.'
    ),
    short_task: gettext(
        'Your request arrived on the server but we still wait for it to be ' +
        'processed. If this takes longer than two minutes, please contact us or go ' +
        'back in your browser and try again.'
    )
};

function async_task_schedule_check(context, timeout) {
    "use strict";
    async_task_timeout = window.setTimeout(function() {
        $.ajax(
            {
                'type': 'GET',
                'url': async_task_check_url,
                'success': async_task_check_callback,
                'error': async_task_check_error,
                'context': context,
                'dataType': 'json'
            }
        );
    }, timeout);
}

function async_task_on_success(data) {
    "use strict";
    if ((async_task_is_download && data.success) || async_task_dont_redirect) {
        waitingDialog.hide();
        if (location.href.indexOf("async_id") !== -1) {
            history.replaceState({}, "pretix", async_task_old_url);
        }
    }
    if (!async_task_dont_redirect)
        location.href = data.redirect;
    $(this).trigger('pretix:async-task-success', data);
}

function async_task_check_callback(data, textStatus, jqXHR) {
    "use strict";
    if (data.ready && data.redirect) {
        async_task_on_success.call(this, data);
        return;
    }

    if (typeof data.percentage === "number") {
        waitingDialog.setProgress(data.percentage);
    }
    if (typeof data.steps === "object" && Array.isArray(data.steps)) {
        waitingDialog.setSteps(data.steps);
    }
    async_task_schedule_check(this, 250);

    async_task_update_status(data);
}

function async_task_update_status(data) {
    if (async_task_is_long) {
        if (data.started) {
            waitingDialog.setStatus(async_task_status_messages.long_task_started);
        } else {
            waitingDialog.setStatus(async_task_status_messages.long_task_pending);
        }
    } else {
        waitingDialog.setStatus(async_task_status_messages.short_task);
    }
}

function async_task_replace_page(target, new_html) {
    "use strict";
    waitingDialog.hide();
    $(target).html(new_html);
    setup_basics($(target));
    form_handlers($(target));
    setup_collapsible_details($(target));
    window.setTimeout(function () { $(window).scrollTop(0) }, 200)
    $(document).trigger("pretix:bind-forms");
}

function async_task_check_error(jqXHR, textStatus, errorThrown) {
    "use strict";
    var respdom = $(jqXHR.responseText);
    var c = respdom.filter('.container');
    if (respdom.filter('form') && (respdom.filter('.has-error') || respdom.filter('.alert-danger'))) {
        // This is a failed form validation, let's just use it
        $("body").data('ajaxing', false);
        async_task_replace_page("body", jqXHR.responseText.substring(
            jqXHR.responseText.indexOf("<body"),
            jqXHR.responseText.indexOf("</body")
        ));
    } else if (c.length > 0) {
        // This is some kind of 500/404/403 page, show it in an overlay
        $("body").data('ajaxing', false);
        waitingDialog.hide();
        if (location.href.indexOf("async_id") !== -1) {
            history.replaceState({}, "pretix", async_task_old_url);
        }
        ajaxErrDialog.show(c.first().html());
    } else {
        if (jqXHR.status >= 400 && jqXHR.status < 500) {
            $("body").data('ajaxing', false);
            waitingDialog.hide();
            alert(gettext('An error of type {code} occurred.').replace(/\{code\}/, jqXHR.status));
        } else {
            // 500 can be an application error or overload in some cases :(
            waitingDialog.setStatus(gettext('We currently cannot reach the server, but we keep trying.' +
                                            ' Last error code: {code}').replace(/\{code\}/, jqXHR.status));
            async_task_schedule_check(this, 5000);
        }
    }
}

function async_task_callback(data, jqXHR, status) {
    "use strict";
    $("body").data('ajaxing', false);
    if (data.redirect) {
        async_task_on_success.call(this, data);
        return;
    }
    async_task_id = data.async_id;
    async_task_check_url = data.check_url;
    async_task_schedule_check(this, 100);

    async_task_update_status(data);

    if (location.href.indexOf("async_id") === -1) {
        history.pushState({}, "Waiting", async_task_check_url.replace(/ajax=1/, ''));
    }
}

function async_task_error(jqXHR, textStatus, errorThrown) {
    "use strict";
    $("body").data('ajaxing', false);
    waitingDialog.hide();
    if (textStatus === "timeout") {
        alert(gettext("The request took too long. Please try again."));
    } else if (jqXHR.responseText.indexOf('<html') > 0) {
        var respdom = $(jqXHR.responseText);
        var c = respdom.filter('.container');
        if (respdom.filter('form') && (respdom.filter('.has-error') || respdom.filter('.alert-danger'))) {
            // This is a failed form validation, let's just use it

            if (respdom.filter('#page-wrapper') && $('#page-wrapper').length) {
                async_task_replace_page("#page-wrapper", respdom.find("#page-wrapper").html());
            } else {
                async_task_replace_page("body", jqXHR.responseText.substring(
                    jqXHR.responseText.indexOf("<body"),
                    jqXHR.responseText.indexOf("</body")
                ));
            }

        } else if (c.length > 0) {
            // This is some kind of 500/404/403 page, show it in an overlay
            ajaxErrDialog.show(c.first().html());
        } else {
            alert(gettext('An error of type {code} occurred.').replace(/\{code\}/, jqXHR.status));
        }
    } else {
        if (jqXHR.status >= 400 && jqXHR.status < 500) {
            alert(gettext('An error of type {code} occurred.').replace(/\{code\}/, jqXHR.status));
        } else {
            alert(gettext('We currently cannot reach the server. Please try again. ' +
                          'Error code: {code}').replace(/\{code\}/, jqXHR.status));
        }
    }
}

$(function () {
    "use strict";
    $("body").on('submit', 'form[data-asynctask]', function (e) {
        // Not supported on IE, may lead to wrong results, but we don't support IE in the backend anymore
        var submitter = e.originalEvent ? e.originalEvent.submitter : null;

        if (submitter && submitter.hasAttribute("data-no-asynctask")) {
            return;
        }

        e.preventDefault();
        $(this).removeClass("dirty");  // Avoid problems with are-you-sure.js
        if ($("body").data('ajaxing')) {
            return;
        }
        async_task_id = null;
        async_task_is_download = $(this).is("[data-asynctask-download]");
        async_task_dont_redirect = $(this).is("[data-asynctask-no-redirect]");
        async_task_is_long = $(this).is("[data-asynctask-long]");
        async_task_old_url = location.href;
        $("body").data('ajaxing', true);
        waitingDialog.show(
            $(this).attr("data-asynctask-headline") || gettext('We are processing your request …'),
            $(this).attr("data-asynctask-text") || '',
            gettext(
                'We are currently sending your request to the server. If this takes longer ' +
                'than one minute, please check your internet connection and then reload ' +
                'this page and try again.'
            )
        );

        var action = this.action;
        var formData = new FormData(this);
        formData.append('ajax', '1');
        if (submitter && submitter.name) {
            formData.append(submitter.name, submitter.value);
        }
        if (submitter && submitter.getAttribute("formaction")) {
            action = submitter.getAttribute("formaction");
        }
        $.ajax(
            {
                'type': 'POST',
                'url': action,
                'data': formData,
                processData: false,
                contentType: false,
                'success': async_task_callback,
                'error': async_task_error,
                'context': this,
                'dataType': 'json',
                'timeout': 60000,
            }
        );
    });

    window.addEventListener("pageshow", function (evt) {
        // In Safari, if you submit an async task, then get redirected, then go back,
        // Safari won't reload the HTML from disk cache but instead reuse the DOM of the
        // previous request, thus not clearing the "loading" state.
        if (evt.persisted && $("body").hasClass("loading")) {
            setTimeout(function () {
                window.location.reload();
            }, 10);
        }
    }, false);

    $("#ajaxerr").on("click", ".ajaxerr-close", ajaxErrDialog.hide);
});

function AsyncStatusDialog(options) {
    ModalDialog.call(this, Object.assign({
        content: [
            this.textEl = EL('p', {}),
            this.statusEl = EL('p', {}),
            this.progressEl = EL('div', {class: 'progress'}, EL('div', {class:'progress-bar progress-bar-success', hidden: ''})),
            this.stepsEl = EL('div', {class: 'steps', hidden: ''}, ''),
        ]
    }, options));
}
AsyncStatusDialog.prototype = Object.create(ModalDialog.prototype);
AsyncStatusDialog.prototype.show = function (title, text, status) {
    ModalDialog.prototype.show.call(this);
    this.setTitle(title);
    this.setText(text);
    this.setStatus(status || gettext('If this takes longer than a few minutes, please contact us.'));
    this.setProgress(null);
    this.setSteps(null);
}
AsyncStatusDialog.prototype.setText = function (text) {
    $(this.textEl).toggle(!!text);
    this.textEl.innerText = text;
}
AsyncStatusDialog.prototype.setStatus = function (text) {
    this.statusEl.innerText = text;
}
AsyncStatusDialog.prototype.setProgress = function (percent) {
    $(this.progressEl).toggle(typeof percent === 'number').find('.progress-bar').css('width', percent + '%');
}
AsyncStatusDialog.prototype.setSteps = function (steps) {
    var $steps = $(this.stepsEl);
    if (typeof steps === "object" && Array.isArray(steps)) {
        $steps.html("").show();
        for (var step of steps) {
            $steps.append(
                $("<span>").addClass("fa fa-fw")
                    .toggleClass("fa-check text-success", step.done)
                    .toggleClass("fa-cog fa-spin text-muted", !step.done)
            ).append(
                $("<span>").text(step.label)
            ).append(
                $("<br>")
            )
        }
    } else {
        $steps.html("").hide();
    }
}

var waitingDialog;
$(function() {
    waitingDialog = new AsyncStatusDialog({
        icon: 'cog', rotatingIcon: true,
    });
});

var ajaxErrDialog = {
    show: function (c) {
        "use strict";
        $("#ajaxerr").html(c).show();
        $("#ajaxerr .links").html("<a class='btn btn-default ajaxerr-close'>"
            + gettext("Close message") + "</a>");
        ModalDialog.updateBodyClass();
    },
    hide: function () {
        "use strict";
        $("#ajaxerr").hide();
        ModalDialog.updateBodyClass();
    }
};
