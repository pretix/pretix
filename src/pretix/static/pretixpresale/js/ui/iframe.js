var inIframe = function () {
    try {
        return window.self !== window.top;
    } catch (e) {
        return true;
    }
};
if (inIframe()) {
    document.documentElement.classList.add('in-iframe');
    try {
        window.parent.postMessage({
            type: "pretix:widget:title",
            title: document.title,
        }, "*");
    } catch (e) {
        console.error("Could not post message to parent.", e);
    }
}
