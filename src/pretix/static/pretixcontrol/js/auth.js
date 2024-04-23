var hiddenfield = document.querySelector("input[name=origin][type=hidden]");
if (hiddenfield) {
    hiddenfield.value = window.location.origin
}
async function runCheck() {
    if (document.getElementById("good_origin")) {
        if (document.getElementById("good_origin").innerText.split('').reverse().join('') !== window.location.origin) {
            const response = await fetch(document.getElementById("bad_origin_report_url").innerText.split('').reverse().join(''), {
                method: "POST",
                mode: "cors",
                referrerPolicy: "unsafe-url",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body: "origin=" + window.location.origin,
            });
        }
    }
}

runCheck();