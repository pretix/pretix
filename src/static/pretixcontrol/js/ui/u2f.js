/*global $,u2f */
$(function () {
    if ($("#u2f-enroll").length) {
        var request = JSON.parse($.trim($("#u2f-enroll").html()));
        setTimeout(function () {
            var appId = request.registerRequests[0].appId;
            $('#promptModal').modal('show');
            console.log(appId, request.registerRequests);
            u2f.register(appId, request.registerRequests, [], function (data) {
                console.log("callback", data);
                if (data.errorCode) {
                    $("#u2f-error").removeClass("sr-only");
                    $("#u2f-progress").remove();
                } else {
                    console.log("Register callback", data);
                    $('#u2f-response').val(JSON.stringify(data));
                    $('#u2f-form').submit();
                }
            });
        }, 500);
    }
});
