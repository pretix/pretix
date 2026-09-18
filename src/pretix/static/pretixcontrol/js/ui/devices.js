$(function () {
	let update = function () {
		$.getJSON(location.href + '?ajax=true', {}, function (data) {
			if (data.initialized) {
				location.reload()
			} else {
				window.setTimeout(update, 500)
			}
		})
	}
	window.setTimeout(update, 500)
})
