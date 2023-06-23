/*global $, waitingDialog, gettext */
var async_task_id = null;
var async_task_timeout = null;
var async_task_check_url = null;
var async_task_old_url = null;
var async_task_is_download = false;
var async_task_is_long = false;

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

function async_task_check_callback(data, textStatus, jqXHR) {
    "use strict";
    if (data.ready && data.redirect) {
        if (async_task_is_download && data.success) {
            waitingDialog.hide();
            if (location.href.indexOf("async_id") !== -1) {
                history.replaceState({}, "pretix", async_task_old_url);
            }
        }
        location.href = data.redirect;
        return;
    } else if (typeof data.percentage === "number") {
        $("#loadingmodal .progress").show();
        $("#loadingmodal .progress .progress-bar").css("width", data.percentage + "%");
        if (typeof data.steps === "object" && Array.isArray(data.steps)) {
            var $steps = $("#loadingmodal .steps");
            $steps.html("").show()
            for (var step of data.steps) {
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
        }
    }
    async_task_timeout = window.setTimeout(async_task_check, 250);

    if (async_task_is_long) {
        if (data.started) {
            $("#loadingmodal p.status").text(gettext(
                'Your request is currently being processed. Depending on the size of your event, this might take up to ' +
                'a few minutes.'
            ));
        } else {
            $("#loadingmodal p.status").text(gettext(
                'Your request has been queued on the server and will soon be ' +
                'processed.'
            ));
        }
    } else {
        $("#loadingmodal p.status").text(gettext(
            'Your request arrived on the server but we still wait for it to be ' +
            'processed. If this takes longer than two minutes, please contact us or go ' +
            'back in your browser and try again.'
        ));
    }
}

function async_task_check_error(jqXHR, textStatus, errorThrown) {
    "use strict";
    var respdom = $(jqXHR.responseText);
    var c = respdom.filter('.container');
    if (respdom.filter('form') && (respdom.filter('.has-error') || respdom.filter('.alert-danger'))) {
        // This is a failed form validation, let's just use it
        $("body").data('ajaxing', false);
        waitingDialog.hide();
        $("body").html(jqXHR.responseText.substring(
            jqXHR.responseText.indexOf("<body"),
            jqXHR.responseText.indexOf("</body")
        ));
        setup_basics($("body"));
        form_handlers($("body"));
        setup_collapsible_details($("body"));
        window.setTimeout(function () { $(window).scrollTop(0) }, 200)
        $(document).trigger("pretix:bind-forms");
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
            $("#loadingmodal p.status").text(gettext('We currently cannot reach the server, but we keep trying.' +
                                              ' Last error code: {code}').replace(/\{code\}/, jqXHR.status));
            async_task_timeout = window.setTimeout(async_task_check, 5000);
        }
    }
}

function async_task_callback(data, jqXHR, status) {
    "use strict";
    $("body").data('ajaxing', false);
    if (data.redirect) {
        if (async_task_is_download && data.success) {
            waitingDialog.hide();
            if (location.href.indexOf("async_id") !== -1) {
                history.replaceState({}, "pretix", async_task_old_url);
            }
        }
        location.href = data.redirect;
        return;
    }
    async_task_id = data.async_id;
    async_task_check_url = data.check_url;
    async_task_timeout = window.setTimeout(async_task_check, 100);

    if (async_task_is_long) {
        if (data.started) {
            $("#loadingmodal p.status").text(gettext(
                'Your request is currently being processed. Depending on the size of your event, this might take up to ' +
                'a few minutes.'
            ));
        } else {
            $("#loadingmodal p.status").text(gettext(
                'Your request has been queued on the server and will soon be ' +
                'processed.'
            ));
        }
    } else {
        $("#loadingmodal p.status").text(gettext(
            'Your request arrived on the server but we still wait for it to be ' +
            'processed. If this takes longer than two minutes, please contact us or go ' +
            'back in your browser and try again.'
        ));
    }
    if (location.href.indexOf("async_id") === -1) {
        history.pushState({}, "Waiting", async_task_check_url.replace(/ajax=1/, ''));
    }
}

function async_task_error(jqXHR, textStatus, errorThrown) {
    "use strict";
    $("body").data('ajaxing', false);
    if (textStatus === "timeout") {
        alert(gettext("The request took too long. Please try again."));
        waitingDialog.hide();
    } else if (jqXHR.responseText.indexOf('<html') > 0) {
        var respdom = $(jqXHR.responseText);
        var c = respdom.filter('.container');
        if (respdom.filter('form') && (respdom.filter('.has-error') || respdom.filter('.alert-danger'))) {
            // This is a failed form validation, let's just use it
            waitingDialog.hide();

            if (respdom.filter('#page-wrapper') && $('#page-wrapper').length) {
                $("#page-wrapper").html(respdom.find("#page-wrapper").html());
                setup_basics($("#page-wrapper"));
                form_handlers($("#page-wrapper"));
                setup_collapsible_details($("#page-wrapper"));
                $(document).trigger("pretix:bind-forms");
                window.setTimeout(function () { $(window).scrollTop(0) }, 200)
            } else {
                $("body").html(jqXHR.responseText.substring(
                    jqXHR.responseText.indexOf("<body"),
                    jqXHR.responseText.indexOf("</body")
                ));
                setup_basics($("body"));
                form_handlers($("body"));
                setup_collapsible_details($("body"));
                $(document).trigger("pretix:bind-forms");
                window.setTimeout(function () { $(window).scrollTop(0) }, 200)
            }

        } else if (c.length > 0) {
            waitingDialog.hide();
            ajaxErrDialog.show(c.first().html());
        } else {
            waitingDialog.hide();
            alert(gettext('An error of type {code} occurred.').replace(/\{code\}/, jqXHR.status));
        }
    } else {
        if (jqXHR.status >= 400 && jqXHR.status < 500) {
            waitingDialog.hide();
            alert(gettext('An error of type {code} occurred.').replace(/\{code\}/, jqXHR.status));
        } else {
            waitingDialog.hide();
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
        async_task_is_long = $(this).is("[data-asynctask-long]");
        async_task_old_url = location.href;
        $("body").data('ajaxing', true);
        if ($(this).is("[data-asynctask-headline]")) {
            waitingDialog.show($(this).attr("data-asynctask-headline"));
        } else {
            waitingDialog.show(gettext('We are processing your request …'));
        }
        if ($(this).is("[data-asynctask-text]")) {
            $("#loadingmodal p.text").text($(this).attr("data-asynctask-text")).show();
        } else {
            $("#loadingmodal p.text").hide();
        }
        $("#loadingmodal p.status").text(gettext(
            'We are currently sending your request to the server. If this takes longer ' +
            'than one minute, please check your internet connection and then reload ' +
            'this page and try again.'
        ));

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
});

var waitingDialog = {
    show: function (message) {
        "use strict";
        $("#loadingmodal h3").html(message);
        $("#loadingmodal .progress").hide();
        $("#loadingmodal .steps").hide();
        $("body").addClass("loading");
        $("#loadingmodal").removeAttr("hidden");
    },
    hide: function () {
        "use strict";
        $("body").removeClass("loading");
        $("#loadingmodal").attr("hidden", true);
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
