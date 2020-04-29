var inIframe = function () {
    try {
        return window.self !== window.top;
    } catch (e) {
        return true;
    }
};
if (inIframe()) {
    document.documentElement.classList.add('in-iframe');
}
