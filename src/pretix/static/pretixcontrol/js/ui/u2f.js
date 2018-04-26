/*global $,u2f */
$(function () {
    $("#u2f-progress").hide();
    if ($("#u2f-enroll").length) {
        var request = JSON.parse($.trim($("#u2f-enroll").html()));
        $("#u2f-progress").show();
        setTimeout(function () {
            var appId = request.registerRequests[0].appId;
            u2f.register(appId, request.registerRequests, [], function (data) {
                if (data.errorCode) {
                    $("#u2f-error").removeClass("sr-only");
                    $("#u2f-progress").remove();
                } else {
                    $('#u2f-response').val(JSON.stringify(data));
                    $('#u2f-form').submit();
                }
            }, 300);
        }, 100);
    } else if ($("#u2f-login").length) {
        var request = JSON.parse($.trim($("#u2f-login").html()));
        $("#u2f-progress").show();
        setTimeout(function () {
            var firstr = request.authenticateRequests[0];
            var appId = firstr.appId;
            var registeredKeys = [];
            var reqs = request.authenticateRequests;
            for (var i = 0; i < reqs.length; i++) {
                registeredKeys.push({version: reqs[i].version, keyHandle: reqs[i].keyHandle});
            }
            u2f.sign(appId, firstr.challenge, registeredKeys, function (data) {
                if (data.errorCode && data.errorCode != 5) {
                    $("#u2f-error").removeClass("sr-only");
                } else {
                    $('#u2f-response, #id_password').val(JSON.stringify(data));
                    $('#u2f-form').submit();
                }
            }, 300);
        }, 100);
    }
});
