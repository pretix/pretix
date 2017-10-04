var inIframe = function () {
    try {
        return window.self !== window.top;
    } catch (e) {
        return true;
    }
};
if (inIframe()) {
    document.body.classList.add('in-iframe');
}
