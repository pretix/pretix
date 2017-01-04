var intId = window.setInterval(function () {
    $.get(location.href + '?ajax=1', function (data, status) {
        if (data === "1") {
            window.clearInterval(intId);
            location.reload();
        }
    });
}, 500);
