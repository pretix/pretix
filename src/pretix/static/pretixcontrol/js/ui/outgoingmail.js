function is_sandbox_supported() {
    const iframe = document.createElement('iframe');
    return 'sandbox' in iframe;
}

function safe_render(url, parent) {
    // Estimate the height that prevents the user from having to scroll on two levels to see the full email
    const height = (
        Math.max(400, window.innerHeight - parent.parent().get(0).getBoundingClientRect().top - document.querySelector("footer").getBoundingClientRect().height - 20)
    ) + "px";

    const iframe = (
        // Per the HTML spec, a data: URL in an iframe is treated as its own origin:
        // https://github.com/whatwg/html/pull/1756
        // It is unclear, if Firefox complies, and the behaviour around data URLs is quite wild:
        // https://github.com/whatwg/html/issues/12091
        // Together with the sandbox attribute disallowing all JavaScript, and the fact
        // that we sanitize the HTML before we even save it to the database, this should
        // still be the safest way to render HTML in the context of our backend.
        $("<iframe>")
            .height(height)
            .attr("class", "html-email")
            .attr("src", url)
            .attr("sandbox", "allow-popups allow-popups-to-escape-sandbox")
            .attr("csp", "script-src 'none'; font-src 'none'; connect-src 'none'; form-action 'none'; style-src 'unsafe-inline'")  // respected only by chrome
            .prop("credentialless", true)  // respected only by chrome
    );

    console.log(parent, iframe);
    parent.append(iframe);
}

$(function () {
    const script_element = $("#mail_body_html");
    if (!script_element.length) return;
    if (!is_sandbox_supported()) {
        // Browser is too old for <iframe sandbox>
        $(script_element.parent()).text("Please switch to a modern browser to view HTML content safely.");
        return;
    }

    safe_render(JSON.parse(script_element.html()), script_element.parent());
});
