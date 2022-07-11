/*global $ */

$(function () {
    window.addEventListener("message", (event) => {
        if (event.data && event.data.__process === "popup_close") {
            window.close()
        }
    });
    window.opener.postMessage(JSON.parse($("#postmessage").text()), $("#origin").text())
})