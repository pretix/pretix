/* global gettext */
var bankimport_transactionlist = {

	_btn_click: function (e) {
		console.log(e.delegateTarget)
		let trans_id = parseInt($(e.delegateTarget).attr('name').split('_')[1])
		let value = $(e.delegateTarget).val()
		if (value === 'discard') {
			bankimport_transactionlist.discard(trans_id)
		} else if (value === 'accept') {
			bankimport_transactionlist.accept(trans_id)
		} else if (value === 'retry') {
			bankimport_transactionlist.retry(trans_id)
		} else if (value === 'assign') {
			bankimport_transactionlist.assign(trans_id)
		}
		return false
	},

	_action: function (id, action, success) {
		$('tr[data-id=' + id + '] button').prop('disabled', true)
		let data = {
			csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()
		}
		data['action_' + id] = action
		$.ajax({
			method: 'POST',
			url: $('.transaction-list').attr('data-url'),
			data: data,
			dataType: 'json',
			success: function (data) {
				if (data.status == 'ok') {
					$('tr[data-id=' + id + ']').removeClass('has-error')
					if (data.comment) {
						bankimport_transactionlist.comment_reset_to_text(id, data.comment, data.plain)
					}
					success()
				} else {
					$('tr[data-id=' + id + '] button').prop('disabled', false)
					$('tr[data-id=' + id + '] .help-block').remove()
					$('tr[data-id=' + id + ']').addClass('has-error')
					$('<p>').addClass('help-block').text(data.message).appendTo($('tr[data-id=' + id + '] td.actions'))
				}
			}
		})
	},

	discard: function (id) {
		bankimport_transactionlist._action(id, 'discard', function () {
			$('tr[data-id=' + id + '] td').remove()
		})
	},

	retry: function (id) {
		bankimport_transactionlist._action(id, 'retry', function () {
			$('tr[data-id=' + id + '] td.actions').html('').text(gettext('Marked as paid'))
		})
	},

	accept: function (id) {
		bankimport_transactionlist._action(id, 'accept', function () {
			$('tr[data-id=' + id + '] td.actions').html('').text(gettext('Marked as paid'))
		})
	},

	assign: function (id) {
		bankimport_transactionlist._action(id, 'assign:' + $('tr[data-id=' + id + '] input.form-control:not(.tt-hint)').val(), function () {
			$('tr[data-id=' + id + '] td.actions').html('').text(gettext('Marked as paid'))
		})
	},

	comment_reset_to_text: function (id, text, plain) {
		let $box = $('tr[data-id=' + id + '] .comment-box')
		$box[0].dataset['plain'] = plain
		$box.html('')
			.append($('<strong>').text(gettext('Comment:')))
			.append(' ')
			.append($('<span>').addClass('comment').append(' ').append(text))
			.append(' ')
			.append($('<a>').addClass('comment-modify btn btn-default btn-xs')
				.append('<span class=\'fa fa-edit\'></span>'))
	},

	comment_start_edit: function (e) {
		let $box = $(e.target).closest('div')
		let id = $box.closest('tr').attr('data-id')
		let $inp = $('<textarea>').addClass('form-control')
		let orig_rendered = $box.find('.comment')
		let orig_text = $box[0].dataset.plain
		$inp.val(orig_text)

		let $btngrp = $('<div>')
		$btngrp.addClass('btn-group')
		let $btn1 = $('<button>')
		$btn1.attr('type', 'button').addClass('btn btn-default')
		$btn1.append('<span class=\'fa fa-check\'></span>')
		$btngrp.append($btn1)
		let $btn2 = $('<button>')
		$btn2.attr('type', 'button').addClass('btn btn-default')
		$btn2.append('<span class=\'fa fa-close\'></span>')
		$btngrp.append($btn2)
		$box.html('').append($inp).append($btngrp)
		$btn1.click(function () {
			let text = $box.find('textarea').val()
			$box.find('input, textarea, button').prop('disabled', true)
			bankimport_transactionlist._action(id, 'comment:' + text, function () {
				$('tr[data-id=' + id + '] button').prop('disabled', false)
			})
		})
		$btn2.click(function () {
			bankimport_transactionlist.comment_reset_to_text(id, orig_rendered, orig_text)
		})

		e.preventDefault()
	},

	typeahead_source: function () {
		return new Bloodhound({
			datumTokenizer: Bloodhound.tokenizers.obj.whitespace('value'),
			queryTokenizer: Bloodhound.tokenizers.whitespace,
			remote: {
				url: $('.transaction-list').attr('data-url'),
				prepare: function (query, settings) {
					settings.url = settings.url + '?query=' + encodeURIComponent(query)
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
		})
	},

	init: function () {
		if ($('.transaction-list').length) {
			$('.transaction-list button').click(bankimport_transactionlist._btn_click)

			$('.transaction-list').on('click', '.comment-modify', bankimport_transactionlist.comment_start_edit)

			$('.transaction-list .form-control').typeahead(null, {
				minLength: 2,
				name: 'order-dataset',
				source: bankimport_transactionlist.typeahead_source(),
				display: function (obj) {
					return obj.code
				},
				templates: {
					suggestion: function (obj) {
						return '<div>' + obj.code + ' (' + obj.total + ', ' + obj.status + ')</div>'
					}
				}
			}).keypress(function (e) {
				if (e.keyCode === 13) {
					$(this).parent().parent().find('button[value=assign]').click()
				}
			})
		}

		if ($('[data-job-waiting]').length) {
			window.setTimeout(bankimport_transactionlist.check_state, 750)
		}
	},

	check_state: function () {
		$.getJSON($('[data-job-waiting-url]').attr('data-job-waiting-url'), function (data) {
			if (data.state == 'running' || data.state == 'pending') {
				window.setTimeout(bankimport_transactionlist.check_state, 750)
			} else {
				location.reload()
			}
		})
	}
}

$(function () {
	bankimport_transactionlist.init()
})
