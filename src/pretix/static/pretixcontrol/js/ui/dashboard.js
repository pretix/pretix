/* global $,gettext */

$(function () {
	if ($('div[data-lazy-id]').length == 0) {
		return
	}
	$.getJSON('widgets.json' + ($('select[name=\'subevent\']').val() ? '?subevent=' + $('select[name=\'subevent\']').val() : ''), function (data) {
		$.each(data.widgets, function (k, v) {
			$('[data-lazy-id=' + v.lazy + ']').removeClass('widget-lazy-loading')
			$('[data-lazy-id=' + v.lazy + '] .widget').html(v.content)
		})
	})
})
$(function () {
	$('.timeline').each(function () {
		let $tl = $(this)
		let $first = $(this).find('.row:not(.text-muted)').first()
		$tl.scrollTop($tl.scrollTop() + Math.max($first.position().top - 50, 0))
	})
})
