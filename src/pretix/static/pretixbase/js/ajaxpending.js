let check = function () {
	$.getJSON(location.href + '&ajax=1', function (data, _status) {
		if (data.redirect) {
			location.href = data.redirect
		} else {
			window.setTimeout(check, 500)
		}
	})
}
window.setTimeout(check, 500)
