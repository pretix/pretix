$(function () {
	let j = 0
	$('.tabbed-form').each(function () {
		let $form = $(this)
		let $tabs = $('<ul>').addClass('nav nav-tabs').insertBefore($form)
		$form.addClass('tab-content')

		let i = 0
		let preselect = null
		let validity_error = false
		$form.find('fieldset').each(function () {
			let $fieldset = $(this)
			let tid = $fieldset.attr('id')
			if (!tid) tid = 'tab-' + j + '-' + i
			let $tabli = $('<li>').appendTo($tabs)
			let $tablink = $('<a>').attr('role', 'tab')
				.attr('data-toggle', 'tab')
				.attr('href', '#' + tid)
				.text($fieldset.find('legend').text())
				.appendTo($tabli)
			if ($fieldset.find('.has-error, .alert-danger:not(.dynamic)').length > 0) {
				$tablink.append(' ')
				$tablink.append($('<span>').addClass('fa fa-warning text-danger'))
				if (preselect === null) {
					preselect = i
				}
			}
			$fieldset.find('input, select, textarea').on('invalid', function () {
				if ($tablink.find('.fa-warning').length === 0) {
					$tablink.append(' ')
					$tablink.append($('<span>').addClass('fa fa-warning text-danger'))
					if (!validity_error) {
						validity_error = true
						$tablink.click()
					}
				}
			})
			$fieldset.find('legend').remove()
			$fieldset.addClass('tab-pane').attr('id', tid)
			if (location.hash && ($fieldset.find(location.hash).length || location.hash === '#' + tid + '-open') && preselect === null) {
				preselect = i
			}
			i++
		})
		$tabs.find('a').get(preselect != null ? preselect : 0).click()
		$tabs.find('a').on('shown.bs.tab', function (e) {
			history.replaceState(null, null, e.target.getAttribute('href') + '-open')
		})
		$form.closest('form').on('submit', function () {
			validity_error = false
		})
		j++
	})
})
