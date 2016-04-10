window.setInterval(function () {
    $.get(location.href + '?ajax=1', function (data, status) {
        if (data === "1") {
            location.reload();
        }
    });
}, 500);
