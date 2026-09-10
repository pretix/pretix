/* global gettext, Bloodhound */

function formatPrice (price, currency, locale) {
	if (!window.Intl || !Intl.NumberFormat) return price
	let priceToFormat = price
	if (currency === undefined) {
		currency = $('[data-currency]').data('currency')
	}
	if (locale === undefined) {
		locale = $('[data-locale]').data('locale') || $('[data-pretixlocale]').data('pretixlocale')
	}

	let opt = currency ? { style: 'currency', currency: currency } : null
	let nf = new Intl.NumberFormat(locale, opt)

	if (isNaN(priceToFormat) && priceToFormat.replaceAll) {
		// price is not a number, try to reformat based on locale/currency-format
		let replacements = {
			group: '',
			decimal: '.'
		}
		// format a dummy number to get parts of formatting and
		// replace group and decimal according to replacements
		// to hopefully get a parsable number
		nf.formatToParts(1234.567).forEach(function (part) {
			if (replacements.hasOwnProperty(part.type)) {
				priceToFormat = priceToFormat.replaceAll(part.value, replacements[part.type])
			}
		})
		if (isNaN(priceToFormat)) return price
	}

	try {
		return nf.format(priceToFormat)
	} catch (error) {
		return price
	}
}

let apiGET = function (url, callback) {
	$.getJSON(url, function (data) {
		callback(data)
	})
}

let i18nToString = function (i18nstring) {
	let locale = $('body').attr('data-pretixlocale')
	if (i18nstring[locale]) {
		return i18nstring[locale]
	} else if (i18nstring['en']) {
		return i18nstring['en']
	}
	for (const key in i18nstring) {
		if (i18nstring[key]) {
			return i18nstring[key]
		}
	}
}

$(document).ajaxError(function (event, jqXHR, settings, thrownError) {
	let c = $(jqXHR.responseText).filter('.container')
	if (jqXHR.status === 401 && jqXHR.getResponseHeader('X-Login-Url')) {
		window.location = jqXHR.getResponseHeader('X-Login-Url') + '?next=' + encodeURIComponent(location.pathname + location.search + location.hash)
	} else if (c.length > 0) {
		waitingDialog.hide()
		ajaxErrDialog.show(c.first().html())
	} else if (thrownError !== 'abort' && thrownError !== '') {
		waitingDialog.hide()
		console.error(event, jqXHR, settings, thrownError)
		alert(gettext('Unknown error.'))
	}
})

let form_handlers = function (el) {
	el.trigger('rescan.areYouSure')
	el.find('[data-formset]').formset(
		{
			animateForms: true,
			reorderMode: 'animate'
		}
	)
	el.find('[data-formset]').on('formAdded', 'div', function (event) {
		form_handlers($(event.target))
	})
	el.find('[data-formset] [data-formset-sort]').on('click', function (event) {
		// Sort forms alphabetically by their first field
		let $formset = $(this).closest('[data-formset]')
		let $forms = $formset.find('[data-formset-form]').not('[data-formset-form-deleted]')
		let compareForms = function (form_a, form_b) {
			let a = $(form_a).find('input:not([name*=-ORDER]):not([name*=-DELETE]):not([name*=-id])').val()
			let b = $(form_b).find('input:not([name*=-ORDER]):not([name*=-DELETE]):not([name*=-id])').val()
			return a.localeCompare(b)
		}
		$forms = $forms.sort(compareForms)
		$forms.each(function (i, form) {
			let $order = $(form).find('[name*=-ORDER]')
			$order.val(i + 1)
		})
		// Trigger visual reorder
		$formset.find('[name*=-ORDER]').first().trigger('change')
	})

	// Vouchers
	el.find('#voucher-bulk-codes-generate').click(function () {
		if (!$('#voucher-bulk-codes-num').get(0).reportValidity())
			return
		let num = $('#voucher-bulk-codes-num').val()
		let prefix = $('#voucher-bulk-codes-prefix').val()
		if (num != '') {
			let url = $(this).attr('data-rng-url')
			$('#id_codes').html('Generating...')
			$('.form-group:has(#voucher-bulk-codes-num)').removeClass('has-error')
			$.getJSON(url + '?num=' + num + '&prefix=' + escape(prefix), function (data) {
				$('#id_codes').val(data.codes.join('\n'))
			})
		} else {
			$('.form-group:has(#voucher-bulk-codes-num)').addClass('has-error')
			$('#voucher-bulk-codes-num').focus()
			setTimeout(function () {
				$('.form-group:has(#voucher-bulk-codes-num)').removeClass('has-error')
			}, 3000)
		}
	})

	el.find('.datetimepicker').each(function () {
		$(this).datetimepicker({
			format: $(this).attr('data-format') ? $(this).attr('data-format') : $('body').attr('data-datetimeformat'),
			locale: $('body').attr('data-datetimelocale'),
			useCurrent: false,
			showClear: !$(this).prop('required'),
			icons: {
				time: 'fa fa-clock-o',
				date: 'fa fa-calendar',
				up: 'fa fa-chevron-up',
				down: 'fa fa-chevron-down',
				previous: $('html').hasClass('rtl') ? 'fa fa-chevron-right' : 'fa fa-chevron-left',
				next: $('html').hasClass('rtl') ? 'fa fa-chevron-left' : 'fa fa-chevron-right',
				today: 'fa fa-screenshot',
				clear: 'fa fa-trash',
				close: 'fa fa-remove'
			}
		})
		if (!$(this).val()) {
			$(this).data('DateTimePicker').viewDate(moment().hour(0).minute(0).second(0))
		}
	})

	el.find('.datepickerfield').each(function () {
		let opts = {
			format: $(this).attr('data-format') ? $(this).attr('data-format') : $('body').attr('data-dateformat'),
			locale: $('body').attr('data-datetimelocale'),
			useCurrent: false,
			showClear: !$(this).prop('required'),
			icons: {
				time: 'fa fa-clock-o',
				date: 'fa fa-calendar',
				up: 'fa fa-chevron-up',
				down: 'fa fa-chevron-down',
				previous: $('html').hasClass('rtl') ? 'fa fa-chevron-right' : 'fa fa-chevron-left',
				next: $('html').hasClass('rtl') ? 'fa fa-chevron-left' : 'fa fa-chevron-right',
				today: 'fa fa-screenshot',
				clear: 'fa fa-trash',
				close: 'fa fa-remove'
			},
		}
		if ($(this).is('[data-min]')) {
			opts['minDate'] = $(this).attr('data-min')
			opts['viewDate'] = $(this).attr('data-min')
		}
		if ($(this).is('[data-max]')) {
			opts['maxDate'] = $(this).attr('data-max')
			opts['viewDate'] = (opts.minDate // if minDate and maxDate are set, use the one closer to now as viewDate
				&& Math.abs(+new Date(opts.minDate) - new Date()) < Math.abs(+new Date(opts.maxDate) - new Date())
			) ? opts.minDate : opts.maxDate
		}
		if ($(this).is('[data-is-payment-date]'))
			opts['daysOfWeekDisabled'] = JSON.parse($('body').attr('data-payment-weekdays-disabled'))
		$(this).datetimepicker(opts).on('dp.hide', function () {
			// when min/max is used in datetimepicker, closing and re-opening the picker opens at the wrong date
			// therefore keep the current viewDate and re-set it after datetimepicker is done hiding
			let $dtp = $(this).data('DateTimePicker')
			let currentViewDate = $dtp.viewDate()
			window.setTimeout(function () {
				$dtp.viewDate(currentViewDate)
			}, 50)
		})
		if ($(this).parent().is('.splitdatetimerow')) {
			$(this).on('dp.change', function (ev) {
				let $timepicker = $(this).closest('.splitdatetimerow').find('.timepickerfield')
				let date = $(this).data('DateTimePicker').date()
				if (date === null) {
					return
				}
				if ($timepicker.val() === '') {
					if (/_(until|end|to)(_|$)/.test($(this).attr('name'))) {
						date.set({ hour: 23, minute: 59, second: 59 })
					} else {
						date.set({ hour: 0, minute: 0, second: 0 })
					}
					$timepicker.data('DateTimePicker').date(date)
				}
			})
		}
	})

	el.find('.timepickerfield').each(function () {
		let opts = {
			format: $(this).attr('data-format') ? $(this).attr('data-format') : $('body').attr('data-timeformat'),
			locale: $('body').attr('data-datetimelocale'),
			useCurrent: false,
			showClear: !$(this).prop('required'),
			icons: {
				time: 'fa fa-clock-o',
				date: 'fa fa-calendar',
				up: 'fa fa-chevron-up',
				down: 'fa fa-chevron-down',
				previous: $('html').hasClass('rtl') ? 'fa fa-chevron-right' : 'fa fa-chevron-left',
				next: $('html').hasClass('rtl') ? 'fa fa-chevron-left' : 'fa fa-chevron-right',
				today: 'fa fa-screenshot',
				clear: 'fa fa-trash',
				close: 'fa fa-remove'
			}
		}
		if ($(this).is('[data-is-payment-date]'))
			opts['daysOfWeekDisabled'] = JSON.parse($('body').attr('data-payment-weekdays-disabled'))
		$(this).datetimepicker(opts)
	})

	el.find('.datetimepicker[data-date-after], .datepickerfield[data-date-after]').each(function () {
		let later_field = $(this),
			earlier_field = $($(this).attr('data-date-after')),
			update = function () {
				let earlier = earlier_field.data('DateTimePicker').date(),
					later = later_field.data('DateTimePicker').date()
				if (earlier === null) {
					earlier = false
				} else if (later !== null && later.isBefore(earlier) && !later.isSame(earlier)) {
					later_field.data('DateTimePicker').date(earlier.add(1, 'h'))
				}
				later_field.data('DateTimePicker').minDate(earlier)
			}
		update()
		earlier_field.on('dp.change', update)
	})

	el.find('.datetimepicker[data-date-default], .datepickerfield[data-date-default]').each(function () {
		let fill_field = $(this),
			default_field = $($(this).attr('data-date-default')),
			show = function () {
				let fill_date = fill_field.data('DateTimePicker').date(),
					default_date = default_field.data('DateTimePicker').date()
				if (fill_date === null) {
					fill_field.data('DateTimePicker').defaultDate(default_date)
				}
			}
		fill_field.on('dp.show', show)
	})

	function luminance (r, g, b) {
		// Algorithm defined as https://www.w3.org/TR/2008/REC-WCAG20-20081211/#relativeluminancedef
		let a = [r, g, b].map(function (v) {
			v /= 255
			return v <= 0.03928
				? v / 12.92
				: Math.pow((v + 0.055) / 1.055, 2.4)
		})
		return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722
	}
	function contrast (rgb1, rgb2) {
		// Algorithm defined at https://www.w3.org/TR/WCAG20-TECHS/G17.html#G17-tests
		let l1 = luminance(rgb1[0], rgb1[1], rgb1[2]) + 0.05,
			l2 = luminance(rgb2[0], rgb2[1], rgb2[2]) + 0.05,
			ratio = l1 / l2
		if (l2 > l1) { ratio = 1 / ratio }
		return ratio.toFixed(1)
	}
	el.find('.colorpickerfield').colorpicker({
		format: 'hex',
		align: 'left',
		customClass: 'colorpicker-2x',
		sliders: {
			saturation: {
				maxLeft: 200,
				maxTop: 200
			},
			hue: {
				maxTop: 200
			},
			alpha: {
				maxTop: 200
			}
		}
	}).not('.no-contrast').on('changeColor create', function (e) {
		if (e.type == 'changeColor' && !e.value) {
			return
		}
		let rgb = $(this).colorpicker('color').toRGB()
		let c = contrast([255, 255, 255], [rgb.r, rgb.g, rgb.b])
		let mark = 'times'
		let $icon = $(this).parent().find('.contrast-icon')
		if ($icon.length === 0 && $(this).parent().find('.contrast-state').length === 0) {
			$(this).parent().append('<div class=\'help-block contrast-state\'></div>')
		}
		let $note = $(this).parent().find('.contrast-state')
		if ($(this).val() === '') {
			$note.remove()
		}
		let icon, text, cls
		if (c > 7) {
			icon = 'fa-check-circle'
			text = gettext('Your color has great contrast and will provide excellent accessibility.')
			cls = 'text-success'
		} else if (c > 4.5) {
			icon = 'fa-info-circle'
			text = gettext('Your color has decent contrast and is sufficient for minimum accessibility requirements.')
			cls = ''
		} else {
			icon = 'fa-warning'
			text = gettext('Your color has insufficient contrast to white. Accessibility of your site will be impacted.')
			cls = 'text-danger'
		}
		if ($icon.length === 0) {
			$note.html('<span class=\'fa fa-fw ' + icon + '\'></span>')
				.append(text)
			$note.removeClass('text-success').removeClass('text-danger').addClass(cls)
		} else {
			$icon.html('<span class=\'fa fa-fw ' + icon + ' ' + cls + '\'></span>')
			$icon.attr('title', text)
			$icon.tooltip('destroy')
			window.setTimeout(function () {
				$icon.tooltip({ title: text })
			}, 250)
		}
	})

	function findDependency (searchString, sourceElement) {
		if (searchString.substr(0, 1) === '<') {
			return $(sourceElement).closest('form, .form-horizontal').find(searchString.substr(1))
		} else {
			return $(searchString)
		}
	}

	el.find('input[data-checkbox-dependency]').each(function () {
		let initially_disabled = $(this).prop('disabled')
		let dependent = $(this),
			dependency = findDependency($(this).attr('data-checkbox-dependency'), this),
			update = function () {
				let enabled = dependency.prop('checked')
				dependent.prop('disabled', !enabled || initially_disabled).closest('.form-group, .form-field-boundary').toggleClass('disabled', !enabled)
				if (!enabled && !dependent.is('[data-checkbox-dependency-visual]')) {
					dependent.prop('checked', false)
					dependent.trigger('change')
				}
			}
		update()
		dependency.on('change', update)
	})

	el.find('select[data-inverse-dependency], input[data-inverse-dependency]').each(function () {
		let dependent = $(this),
			dependency = findDependency($(this).attr('data-inverse-dependency'), this),
			update = function () {
				let enabled = !dependency.prop('checked')
				dependent.prop('disabled', !enabled).closest('.form-group, .form-field-boundary').toggleClass('disabled', !enabled)
			}
		update()
		dependency.on('change', update)
	})

	el.find('div[data-display-dependency], textarea[data-display-dependency], input[data-display-dependency], select[data-display-dependency], button[data-display-dependency]').each(function () {
		let initially_disabled = $(this).prop('disabled')
		let dependent = $(this),
			dependency = findDependency($(this).attr('data-display-dependency'), this),
			update = function (ev) {
				let enabled = dependency.toArray().some(function (d) {
					if (d.disabled && !initially_disabled) return false
					if (d.type === 'checkbox' || d.type === 'radio') {
						return d.checked
					} else if (d.type === 'select-one') {
						let checkValue
						if ((checkValue = /^\/(.*)\/$/.exec(dependent.attr('data-display-dependency-regex')))) {
							return new RegExp(checkValue[1]).test(d.value)
						} else if ((checkValue = dependent.attr('data-display-dependency-value'))) {
							return d.value === checkValue
						} else {
							return !!d.value
						}
					} else {
						return (!!d.value && !d.value.match(/^0\.?0*$/g))
					}
				})
				if (dependent.is('[data-inverse]')) {
					enabled = !enabled
				}
				let $toggling = dependent
				if (dependent.is('[data-disable-dependent]')) {
					$toggling.attr('disabled', !enabled || initially_disabled).trigger('change')
				}
				const tagName = dependent.get(0).tagName.toLowerCase()
				if (tagName !== 'div' && tagName !== 'button') {
					$toggling = dependent.closest('.form-group')
				}
				if (ev) {
					if (enabled) {
						$toggling.stop().slideDown()
					} else {
						$toggling.stop().slideUp()
					}
				} else {
					$toggling.stop().toggle(enabled)
				}
			}
		update()
		dependency.each(function () {
			$(this).closest('.form-group').find('[name=' + $(this).attr('name') + ']').on('change dp.change', update)
		})
	})

	el.find('input[data-required-if], select[data-required-if], textarea[data-required-if]').each(function () {
		let dependent = $(this),
			dependencies = $($(this).attr('data-required-if')),
			update = function (ev) {
				let enabled = true
				dependencies.each(function () {
					let dependency = $(this)
					let e = (dependency.attr('type') === 'checkbox' || dependency.attr('type') === 'radio') ? dependency.prop('checked') : !!dependency.val()
					enabled = enabled && e
				})
				dependent.prop('required', enabled).closest('.form-group').toggleClass('required', enabled).find('.optional').stop().animate({
					opacity: enabled ? 0 : 1
				}, ev ? 500 : 1)
			}
		update()
		dependencies.each(function () {
			let dependency = $(this)
			dependency.closest('.form-group').find('input[name=' + dependency.attr('name') + ']').on('change', update)
			dependency.closest('.form-group').find('input[name=' + dependency.attr('name') + ']').on('dp.change', update)
		})
	})

	el.find('div.scrolling-choice:not(.no-search)').each(function () {
		if ($(this).find('input[type=text]').length > 0) {
			return
		}
		let $menu = $('<div>').addClass('choice-options-menu')
		let $inp_search = $('<input>').addClass('form-control').attr('type', 'text').attr('placeholder', gettext('Search query'))
		$menu.append($inp_search)
		$(this).prepend($menu)

		$inp_search.on('keyup change', function (e) {
			let term = $inp_search.val().toLowerCase()

			$(this).closest('.scrolling-choice').find('div.radio').each(function () {
				$(this).toggleClass('hidden', !$(this).text().toLowerCase().includes(term))
			})
		})
	})

	el.find('div.scrolling-multiple-choice').each(function () {
		if ($(this).find('.choice-options-all').length > 0) {
			return
		}
		let $menu = $('<div>').addClass('choice-options-menu')
		let $a_all = $('<a>').addClass('choice-options-all').attr('href', '#').text(gettext('All'))
		let $a_none = $('<a>').addClass('choice-options-none').attr('href', '#').text(gettext('None'))
		let $inp_search = $('<input>').addClass('form-control').attr('type', 'text').attr('placeholder', gettext('Search query'))
		let $lbl_tgl = $('<div>').addClass('checkbox menu-checkbox')
		let $cb_tgl = $('<input>').attr('type', 'checkbox').addClass('menu-checkbox')
		$lbl_tgl.append($('<label>').append($cb_tgl).append(gettext('Selected only')))
		$menu.append($('<span>').append($a_all).append(' / ').append($a_none))
		if (!$(this).is('.no-search')) {
			$menu.append($inp_search)
			$menu.append($lbl_tgl)
		}
		$(this).prepend($menu)

		$(this).find('.choice-options-none').click(function (e) {
			$(this).closest('.scrolling-multiple-choice').find('input[type=checkbox]:not(.menu-checkbox)').prop('checked', false)
			$cb_tgl.trigger('change')
			e.preventDefault()
			return false
		})
		$(this).find('.choice-options-all').click(function (e) {
			$(this).closest('.scrolling-multiple-choice').find('input[type=checkbox]:not(.menu-checkbox)').prop('checked', true)
			$cb_tgl.trigger('change')
			e.preventDefault()
			return false
		})
		$cb_tgl.on('change', function (e) {
			let tgl = $cb_tgl.prop('checked')

			$(this).closest('.scrolling-multiple-choice').find('div.checkbox:not(.menu-checkbox)').each(function () {
				$(this).toggleClass('sr-only', tgl && !$(this).find('input[type=checkbox]').prop('checked'))
			})
		})
		$inp_search.on('keyup change', function (e) {
			let term = $inp_search.val().toLowerCase()

			$(this).closest('.scrolling-multiple-choice').find('div.checkbox:not(.menu-checkbox)').each(function () {
				$(this).toggleClass('hidden', !$(this).text().toLowerCase().includes(term))
			})
		})
	})

	el.find('.select2-static').select2({
		theme: 'bootstrap',
		language: $('body').attr('data-select2-locale'),
	})

	el.find('[data-model-select2=json_script]').each(function () {
		const selectedValue = this.value
		this.replaceChildren()
		$(this).select2({
			theme: 'bootstrap',
			language: $('body').attr('data-select2-locale'),
			data: JSON.parse($(this.getAttribute('data-select2-src')).text()),
			width: '100%',
		}).val(selectedValue).trigger('change')
	})

	el.find('input[data-typeahead-url]').each(function () {
		let $inp = $(this)
		if ($inp.data('ttTypeahead') || $inp.hasClass('tt-hint')) {
			// Already initialized on this element
			return
		}
		$inp.typeahead(null, {
			minLength: 1,
			highlight: true,
			source: new Bloodhound({
				datumTokenizer: Bloodhound.tokenizers.obj.whitespace('value'),
				queryTokenizer: Bloodhound.tokenizers.whitespace,
				remote: {
					url: $inp.attr('data-typeahead-url'),
					prepare: function (query, settings) {
						let sep = (settings.url.indexOf('?') > 0) ? '&' : '?'
						settings.url = settings.url + sep + 'q=' + encodeURIComponent(query)
						return settings
					},
					transform: function (object) {
						let results = object.results
						let suggs = []
						let reslen = results.length
						for (let i = 0; i < reslen; i++) {
							suggs.push(results[i])
						}
						return suggs
					}
				}
			}),
			display: function (obj) {
				return obj.name
			},
		})
	})

	el.find('[data-model-select2=generic]').each(function () {
		let $s = $(this)
		$s.select2({
			closeOnSelect: !this.hasAttribute('multiple'),
			theme: 'bootstrap',
			delay: 100,
			allowClear: !$s.prop('required'),
			width: '100%',
			language: $('body').attr('data-select2-locale'),
			placeholder: $(this).attr('data-placeholder') || '',
			ajax: {
				url: $(this).attr('data-select2-url'),
				data: function (params) {
					return {
						query: params.term,
						page: params.page || 1
					}
				}
			},
			templateResult: function (res) {
				if (!res.id) {
					return res.text
				}
				let $ret = $('<span>').append(
					$(res.inactive ? '<strike class=\'text-muted\'>' : '<span>').addClass('primary').append($('<div>').text(res.text).html())
				)
				if (res.event) {
					$ret.append(
						$('<span>').addClass('secondary').append(
							$('<span>').addClass('fa fa-calendar fa-fw')
						).append(' ').append($('<div>').text(res.event).html())
					)
				}
				return $ret
			},
		}).on('select2:select', function () {
			// Allow continuing to select
			if ($s[0].hasAttribute('multiple')) {
				window.setTimeout(function () {
					$s.parent().find('.select2-search__field').focus()
				}, 50)
			}
		})
		if ($s[0].hasAttribute('data-close-on-clear')) {
			$s.on('select2:clear', function () {
				window.setTimeout(function () {
					$s.select2('close')
				}, 50)
			})
		}
	})

	el.find('[data-model-select2=event]').each(function () {
		let $s = $(this)
		$s.select2({
			closeOnSelect: !this.hasAttribute('multiple'),
			theme: 'bootstrap',
			delay: 100,
			allowClear: !$s.prop('required'),
			width: '100%',
			language: $('body').attr('data-select2-locale'),
			ajax: {
				url: $(this).attr('data-select2-url'),
				data: function (params) {
					return {
						query: params.term,
						page: params.page || 1
					}
				}
			},
			placeholder: $(this).attr('data-placeholder') || '',
			templateResult: function (res) {
				if (!res.id) {
					return res.text
				}
				let $ret = $('<span>').append(
					$('<span>').addClass('event-name-full').append($('<div>').text(res.name).html())
				)
				if (res.organizer) {
					$ret.append(
						$('<span>').addClass('event-organizer').append(
							$('<span>').addClass('fa fa-users fa-fw')
						).append(' ').append($('<div>').text(res.organizer).html())
					)
				}
				if (res.date_range) {
					$ret.append(
						$('<span>').addClass('event-daterange').append(
							$('<span>').addClass('fa fa-calendar fa-fw')
						).append(' ').append(res.date_range)
					)
				}
				return $ret
			},
		}).on('select2:select', function () {
			// Allow continuing to select
			window.setTimeout(function () {
				$s.parent().find('.select2-search__field').focus()
			}, 50)
		})
	})

	el.find('.simple-subevent-choice').change(function () {
		$(this).closest('form').submit()
	})

	el.find('input[name=basics-slug]').bind('keyup keydown change', function () {
		$(this).closest('.form-group').find('.slug-length').toggle($(this).val().length > 16)
	})

	el.find('script[data-replace-with-qr]').each(function () {
		let $div = $('<div>')
		let qrText = this.getAttribute('type') === 'application/json' && this.textContent.startsWith('"')
			? JSON.parse(this.textContent)
			: $(this).html()
		$div.insertBefore($(this))
		$div.qrcode(
			{
				text: qrText,
				correctLevel: 0, // M
				width: $(this).attr('data-size') ? parseInt($(this).attr('data-size')) : 256,
				height: $(this).attr('data-size') ? parseInt($(this).attr('data-size')) : 256,
			}
		)
	})

	el.find('.bulk-edit-field-group').each(function () {
		let $checkbox = $(this).find('input[type=checkbox][name=_bulk]')
		let $content = $(this).find('.field-content')
		let $fields = $content.find('input, select, textarea, button')
		let $dialog = $(this).attr('data-confirm-dialog') ? $($(this).attr('data-confirm-dialog')) : null
		let warningShown = false

		if ($dialog) {
			$dialog.on('close', function () {
				if ($dialog.get(0).returnValue === 'yes') {
					$checkbox.prop('checked', true)
				} else {
					$checkbox.prop('checked', false)
					warningShown = false
				}
				update()
			})
		}

		var update = function () {
			let isChecked = $checkbox.prop('checked')

			$content.toggleClass('enabled', isChecked)
			$fields.attr('tabIndex', isChecked ? 0 : -1)
		}
		$content.on('focusin change click', function () {
			if ($checkbox.prop('checked')) return
			if ($dialog && !warningShown) {
				warningShown = true
				$dialog.get(0).showModal()
			} else {
				$checkbox.prop('checked', true)
				update()
			}
		})
		$checkbox.on('change', function () {
			let isChecked = $checkbox.prop('checked')
			if (isChecked && $dialog && !warningShown) {
				warningShown = true
				$dialog.get(0).showModal()
			} else if (!isChecked) {
				warningShown = false
			}
			update()
		})
		update()
	})

	el.find('input[name*=question], select[name*=question]').change(questions_toggle_dependent)
	questions_toggle_dependent()
	questions_init_photos(el)

	let lastFocusedInput
	$(document).on('focusin', 'input, textarea', function (e) {
		lastFocusedInput = e.target
	}).on('click', function (e) {
		if (e.target.classList.contains('content-placeholder')) {
			let container = e.target.closest('.form-group')
			if (!lastFocusedInput || !container.contains(lastFocusedInput)) {
				lastFocusedInput = container.querySelector('input, textarea')
				// lastFocusedInput.selectionStart = lastFocusedInput.selectionEnd = lastFocusedInput.value.length;
			}
			if (lastFocusedInput) {
				let start = lastFocusedInput.selectionStart
				let end = lastFocusedInput.selectionEnd
				let v = lastFocusedInput.value
				let p = e.target.textContent
				let phStart = /\{\w*$/.exec(v.substring(0, start))
				let phEnd = /^\w*\}/.exec(v.substring(end))
				if (phStart) {
					start -= phStart[0].length
				}
				if (phEnd) {
					end += phEnd[0].length
				}

				lastFocusedInput.value = v.substring(0, start) + p + v.substring(end)
				lastFocusedInput.selectionStart = start
				lastFocusedInput.selectionEnd = start + p.length
				lastFocusedInput.focus()
			}
		}
	})
}

function setup_basics (el) {
	el.find('#sumtoggle').find('button').click(function () {
		$('.table-product-overview .sum-gross').toggle($(this).attr('data-target') === '.sum-gross')
		$('.table-product-overview .sum-net').toggle($(this).attr('data-target') === '.sum-net')
		$('.table-product-overview .count').toggle($(this).attr('data-target') === '.count')

		$('#sumtoggle').find('button').not($(this)).removeClass('active')
		$(this).addClass('active')
	})

	el.find('.collapsible').collapse()
	el.find('input[data-toggle=radiocollapse]').change(function () {
		$($(this).attr('data-parent')).find('.collapse.in').collapse('hide')
		$($(this).attr('data-target')).collapse('show')
	})
	el.find('div.collapsed').removeClass('collapsed').addClass('collapse')
	el.find('.has-error, .panel-body .alert-danger:not(:has(.has-error))').each(function () {
		let $this = $(this)
		let $panel = $this.closest('div.panel-collapse').collapse('show')
		let alert = el.find('.alert-danger').get(0)
		if (alert === this) {
			return
		}
		let label = ''
		let description = ''
		let scrollTarget = null
		if ($this.hasClass('alert-danger')) {
			// just a general error messages without a actual errorenous input
			label = $this.closest('.panel').find('.panel-title').contents().filter(function () { return this.nodeType == Node.TEXT_NODE }).text()
			description = $this.text()
			scrollTarget = $this.closest('.panel').get(0)
			if (!scrollTarget.id) {
				scrollTarget.id = 'panel_' + $('input', scrollTarget).attr('id')
			}
		} else {
			label = $('label', this).first().contents().filter(function () { return this.nodeType != Node.ELEMENT_NODE || !this.classList.contains('optional') }).text()
			description = $('.help-block', this).first().text()
			scrollTarget = $(':input', this).get(0)
		}

		if (!alert || !scrollTarget) {
			return
		}

		$('<li><a href="#' + scrollTarget.id + '">' + $.trim(label) + '</a> – ' + description + '</li>')
			.appendTo(alert.querySelector('ul') || $('<ul>').appendTo(alert))
			.find('a').on('click', function (e) {
				$panel.collapse('show')
				let tab = scrollTarget.closest('.tab-pane')
				if (tab) {
					$('.nav-tabs a[href=\'#' + tab.id + '\']').click()
				}
				scrollTarget.scrollIntoView()
				scrollTarget.focus()
			})
	})

	el.find('[data-toggle="tooltip"]').tooltip()
	el.find('[data-toggle="tooltip_html"]').tooltip({
		html: true,
		whiteList: {
			// Global attributes allowed on any supplied element below.
			'*': ['class', 'dir', 'id', 'lang', 'role'],
			b: [],
			br: [],
			code: [],
			div: [], // required for template
			h3: ['class', 'role'], // required for template
			i: [],
			small: [],
			span: [],
			strong: [],
			u: [],
		}
	})

	el.find('a.pagination-selection').click(function (e) {
		e.preventDefault()
		let max = parseInt($(this).data('max'))
		let inp = prompt(gettext('Enter page number between 1 and %(max)s.').replace('%(max)s', max))
		if (inp) {
			if (!parseInt(inp) || parseInt(inp) < 1 || parseInt(inp) > max) {
				alert(gettext('Invalid page number.'))
			} else {
				location.href = $(this).attr('data-href').replace('_PAGE_', inp)
			}
		}
	})

	let url = document.location.toString()
	if (url.match('#')) {
		$('.nav-tabs a[href="#' + url.split('#')[1] + '"]').tab('show')
	}
	el.find('a[data-toggle="tab"]').on('click', function (e) {
		if (!$(this).closest('.tab-content').length) {
			// only append hash if not inside a .panel
			window.location.hash = this.hash
		}
	})

	// Event wizard
	el.find('#event-slug-random-generate').click(function () {
		let url = $(this).attr('data-rng-url')
		$('#id_basics-slug').val('Generating...')
		$.getJSON(url, function (data) {
			$('#id_basics-slug').val(data.slug)
		})
	})

	el.find('.propagated-settings-box').find('input, textarea, select').not('[readonly]')
		.attr('data-propagated-locked', 'true').prop('readonly', true)

	el.find('.propagated-settings-box button[data-action=unlink]').click(function (ev) {
		let $box = $(this).closest('.propagated-settings-box')
		$box.find('input[name=decouple]').val($(this).val())
		$box.find('[data-propagated-locked]').prop('readonly', false)
		$box.removeClass('locked').addClass('unlocked')
		ev.preventDefault()
		return true
	})

	// Tables with bulk selection, e.g. subevent list
	el.find('input[data-toggle-table]').each(function (ev) {
		let $toggle = $(this)
		let $actionButtons = $('.batch-select-actions button', this.form)
		let countLabels = $('<span></span>').appendTo($actionButtons.filter(function () { return !$(this).closest('.dropdown-menu').length }))
		let $table = $toggle.closest('table')
		let $selectAll = $table.find('.table-select-all')
		let $rows = $table.find('tbody tr')
		let $checkboxes = $rows.find('td:first-child input[type=checkbox]')
		let firstIndex, lastIndex, selectionChecked, onChangeSelectionHappened = false
		let updateSelection = function (a, b, checked) {
			if (a > b) {
				// [a, b] = [b, a];// ES6 not ready yet for pretix
				let tmp = a
				a = b
				b = tmp
			}
			for (let i = a; i <= b; i++) {
				let checkbox = $checkboxes.get(i)
				if (!checkbox.hasAttribute('data-inital')) checkbox.setAttribute('data-inital', checkbox.checked)
				if (checked === undefined || checked === null) checkbox.checked = checkbox.getAttribute('data-inital') === 'true'
				else checkbox.checked = checked
			}
		}
		let onChangeSelection = function (ev) {
			onChangeSelectionHappened = true

			let row = ev.target.closest('tr')
			let currentIndex = 0
			while (row = row.previousSibling) {
				if (row.tagName) currentIndex++
			}
			let dCurrent = currentIndex - firstIndex
			let dLast = lastIndex - firstIndex
			if (dCurrent * dLast < 0) {
				// direction of selection changed => reset all previously selected
				updateSelection(lastIndex, firstIndex)
			} else if (Math.abs(dCurrent) < Math.abs(dLast)) {
				// selection distance decreased => reset unselected
				updateSelection(currentIndex, lastIndex)
			}
			lastIndex = currentIndex
			updateSelection(firstIndex, currentIndex, selectionChecked)

			ev.preventDefault()
		}
		$table.on('pointerdown', function (ev) {
			if (!ev.target.closest('td:first-child')) return
			let row = ev.target.closest('tr')
			selectionChecked = !row.querySelector('td:first-child input').checked

			firstIndex = 0
			while (row = row.previousSibling) {
				if (row.tagName) firstIndex++
			}
			lastIndex = firstIndex

			ev.preventDefault()
			$rows.on('pointerenter', onChangeSelection)

			$(document).one('pointerup', function (ev) {
				if (onChangeSelectionHappened) {
					ev.preventDefault()
					onChangeSelectionHappened = false
					$checkboxes.removeAttr('data-inital')

					update()
				}
				$rows.off('pointerenter', onChangeSelection)
			})
		})

		var update = function () {
			let nrOfChecked = $checkboxes.filter(':checked').length
			let allChecked = nrOfChecked == $checkboxes.length

			if (!nrOfChecked) countLabels.empty()
			else countLabels.text(' (' + nrOfChecked + ')')

			if (!allChecked) $selectAll.find('input').prop('checked', false)

			$actionButtons.attr('disabled', !nrOfChecked)
			$toggle.prop('checked', allChecked).prop('indeterminate', nrOfChecked > 0 && !allChecked)
			$selectAll.toggleClass('hidden', nrOfChecked !== $checkboxes.length).prop('hidden', nrOfChecked !== $checkboxes.length)
		}

		$checkboxes.change(update)
		$toggle.change(function (ev) {
			this.indeterminate = false
			$checkboxes.prop('checked', this.checked)
			update()
		})
		$selectAll.find('input').change(function (ev) {
			if (this.checked) countLabels.text(' (' + this.getAttribute('data-results-total') + ')')
			else countLabels.text(' (' + $checkboxes.filter(':checked').length + ')')
		})

		update()
	})

	// Items and categories
	el.find('.internal-name-wrapper').each(function () {
		if ($(this).find('input').val() === '') {
			let $fg = $(this).find('.form-group')
			$fg.hide()
			var $fgl = $('<div>').addClass('form-group').append(
				$('<div>').addClass('col-md-9 col-md-offset-3').append(
					$('<div>').addClass('help-block').append(
						$('<a>').attr('href', '#').text(
							gettext('Use a different name internally')
						).click(function () {
							$fg.slideDown()
							$fgl.slideUp()
							return false
						})
					)
				)
			)
			$(this).append($fgl)
		}
	})

	el.find('button[data-toggle=qrcode]').click(function (e) {
		e.preventDefault()
		let $current = $('.qr-code-overlay[data-qrcode=\'' + $(this).attr('data-qrcode') + '\']')
		if ($current.length) {
			$('.qr-code-overlay').attr('data-qrcode', '').slideUp(200)
			return false
		}
		$('.qr-code-overlay').remove()
		let $div = $('<div>').addClass('qr-code-overlay').attr('data-qrcode', $(this).attr('data-qrcode'))
		$div.appendTo($('body'))
		let offset = $(this).offset()
		$div.css('top', offset.top + $(this).outerHeight() + 10).css('left', offset.left)
		let $child = $('<div>')
		$child.appendTo($div)
		$child.qrcode(
			{
				text: $(this).attr('data-qrcode'),
				correctLevel: 0, // M
				width: 196,
				height: 196
			}
		)
		let $inner = $('<div>').text($(this).attr('data-qrcode').slice(0, 10) + '…')
		$inner.append($('<btn>').addClass('btn btn-link btn-xs btn-clipboard').attr('data-clipboard-text', $(this).attr('data-qrcode')).append(
			$('<span>').addClass('fa fa-clipboard').attr('aria-hidden', 'true')
		))
		$div.append($inner.get(0).innerHTML + '<br>')
		$div.append(gettext('Click to close'))
		$div.slideDown(200)
		$div.click(function (e) {
			if ($(e.target).closest('.btn').length) {
				return
			}
			$('.qr-code-overlay').attr('data-qrcode', '').slideUp(200)
		})
		return false
	})
}

$(function () {
	'use strict'

	$('body').removeClass('nojs')
	lightbox.init()

	$(document).on('click', '.variations .variations-select-all', function (e) {
		$(this).parent().parent().find('input[type=checkbox]').prop('checked', true).change()
		e.stopPropagation()
		return false
	})
	$(document).on('click', '.variations .variations-select-none', function (e) {
		$(this).parent().parent().find('input[type=checkbox]').prop('checked', false).change()
		e.stopPropagation()
		return false
	})
	if ($('.items-on-quota').length) {
		$('.items-on-quota .panel').each(function () {
			let $panel = $(this)
			$panel.toggleClass('panel-success', $panel.find('input:checked').length > 0)
			$(this).find('input').change(function () {
				$panel.toggleClass('panel-success', $panel.find('input:checked').length > 0)
			})
		})
	}

	setup_basics($('body'))
	form_handlers($('body'))
	$(document).trigger('pretix:bind-forms')

	$('#ajaxerr').on('click', '.ajaxerr-close', ajaxErrDialog.hide)
	moment.locale($('body').attr('data-datetimelocale'))
	add_log_expand_handlers($('body'))
})

function add_log_expand_handlers (el) {
	el.find('a[data-expandlogs], a[data-expandrefund], a[data-expandpayment]').click(function (e) {
		e.preventDefault()
		let $a = $(this)
		let id = $(this).attr('data-id')
		$a.find('.fa').removeClass('fa-eye').addClass('fa-cog fa-spin')
		let url = '/control/logdetail/'
		if ($a.is('[data-expandrefund]')) {
			url += 'refund/'
		} else if ($a.is('[data-expandpayment]')) {
			url += 'payment/'
		}
		function format_data (data) {
			return Object.entries(data).map(([key, value]) =>
				$('<div>').append(
					$('<b>').text(key + ': '),
					$('<span>').text(JSON.stringify(value, null, 2))))
		}
		$.getJSON(url + '?pk=' + id, function (data) {
			if ($a.parent().tagName === 'p') {
				$('<pre>').append(format_data(data)).insertAfter($a.parent())
			} else {
				$('<pre>').append(format_data(data)).appendTo($a.parent())
			}
			$a.remove()
		})
		return false
	})
}

$(function () {
	$('form[method=post]').filter(function () {
		return $(this).find('button:not([type=button]), input[type=submit]').length > 0
	}).areYouSure({ message: gettext('You have unsaved changes!') })
})
