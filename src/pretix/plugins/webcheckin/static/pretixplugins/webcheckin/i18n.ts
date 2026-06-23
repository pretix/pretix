const body = document.body

export const timezone = body.dataset.timezone ?? 'UTC'
export const datetimeFormat = body.dataset.datetimeformat ?? 'L LT'
export const dateFormat = body.dataset.dateformat ?? 'L'
export const timeFormat = body.dataset.timeformat ?? 'LT'
export const datetimeLocale = body.dataset.datetimelocale ?? 'en'
export const pretixLocale = body.dataset.pretixlocale ?? 'en'

moment.locale(datetimeLocale)

export function gettext (msgid: string): string {
	if (typeof django !== 'undefined' && typeof django.gettext !== 'undefined') {
		return django.gettext(msgid)
	}
	return msgid
}

export function ngettext (singular: string, plural: string, count: number): string {
	if (typeof django !== 'undefined' && typeof django.ngettext !== 'undefined') {
		return django.ngettext(singular, plural, count)
	}
	return plural
}

export type I18nString = string | Record<string, string> | null | undefined

export function i18nstringLocalize (obj: I18nString): string {
	// external
	return i18nstring_localize(obj)
}

export const STRINGS: Record<string, string> = {
	'checkinlist.select': gettext('Select a check-in list'),
	'checkinlist.none': gettext('No active check-in lists found.'),
	'checkinlist.switch': gettext('Switch check-in list'),
	'results.headline': gettext('Search results'),
	'results.none': gettext('No tickets found'),
	'check.headline': gettext('Result'),
	'check.attention': gettext('This ticket requires special attention'),
	'scantype.switch': gettext('Switch direction'),
	'scantype.entry': gettext('Entry'),
	'scantype.exit': gettext('Exit'),
	'input.placeholder': gettext('Scan a ticket or search and press return…'),
	'pagination.next': gettext('Load more'),
	'status.p': gettext('Valid'),
	'status.n': gettext('Unpaid'),
	'status.c': gettext('Canceled'),
	'status.e': gettext('Canceled'),
	'status.pending_valid': gettext('Confirmed'),
	'status.require_approval': gettext('Approval pending'),
	'status.redeemed': gettext('Redeemed'),
	'modal.cancel': gettext('Cancel'),
	'modal.continue': gettext('Continue'),
	'modal.unpaid.head': gettext('Ticket not paid'),
	'modal.unpaid.text': gettext('This ticket is not yet paid. Do you want to continue anyways?'),
	'modal.questions': gettext('Additional information required'),
	'result.ok': gettext('Valid ticket'),
	'result.exit': gettext('Exit recorded'),
	'result.already_redeemed': gettext('Ticket already used'),
	'result.questions': gettext('Information required'),
	'result.invalid': gettext('Unknown ticket'),
	'result.product': gettext('Ticket type not allowed here'),
	'result.unpaid': gettext('Ticket not paid'),
	'result.rules': gettext('Entry not allowed'),
	'result.revoked': gettext('Ticket code revoked/changed'),
	'result.blocked': gettext('Ticket blocked'),
	'result.invalid_time': gettext('Ticket not valid at this time'),
	'result.canceled': gettext('Order canceled'),
	'result.ambiguous': gettext('Ticket code is ambiguous on list'),
	'result.unapproved': gettext('Order not approved'),
	'status.checkin': gettext('Checked-in Tickets'),
	'status.position': gettext('Valid Tickets'),
	'status.inside': gettext('Currently inside'),
	yes: gettext('Yes'),
	no: gettext('No'),
}

export interface SubEvent {
	name: Record<string, string>
	date_from: string
}

export function formatSubevent (subevent: SubEvent | null | undefined): string {
	if (!subevent) return ''
	const name = i18nstringLocalize(subevent.name)
	const date = moment.utc(subevent.date_from).tz(timezone).format(datetimeFormat)
	return `${name} · ${date}`
}

export interface Question {
	type: string
}

export function formatAnswer (value: string, question: Question): string {
	if (question.type === 'B' && value === 'True') {
		return STRINGS['yes']
	} else if (question.type === 'B' && value === 'False') {
		return STRINGS['no']
	} else if (question.type === 'W' && value) {
		return moment(value).tz(timezone).format('L LT')
	} else if (question.type === 'D' && value) {
		return moment(value).format('L')
	}
	return value
}
