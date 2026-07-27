/* global $,gettext */

$(function () {
	$('.timeline').each(function () {
		let $tl = $(this)
		let $first = $(this).find('.row:not(.text-muted)').first()
		$tl.scrollTop($tl.scrollTop() + Math.max($first.position().top - 50, 0))
	})
})
