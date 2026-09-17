try {
	window.parent.postMessage({
		type: 'pretix:notify-parent',
		data: JSON.parse(document.getElementById('notify_info').textContent),
	}, location.origin)
} catch (e) {
	console.error('Could not post message to parent.', e)
}
