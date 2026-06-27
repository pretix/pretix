// Attempt to auto-open page in new tab. Will be ignored by most browser's popup blockers anyways, though.
var url = JSON.parse(document.getElementById('framebreak-url').innerText)
window.open(url)
