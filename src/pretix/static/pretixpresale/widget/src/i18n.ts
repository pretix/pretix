// Internationalization strings for the pretix widget
// In production, widget.py injects the `django` global before this script loads.
// In dev mode, Django's i18n file expects `this` to be the global object, but
// ES modules have `this` as undefined — so we import as raw text and execute
// with a local context.

interface Django {
	pgettext: (context: string, text: string) => string
	gettext: (text: string) => string
	interpolate: (fmt: string, obj: Record<string, unknown> | unknown[], named?: boolean) => string
	get_format: (formatType: string) => string | number
}

let django: Django

if (import.meta.env.DEV) {
	// TODO this does not actually grab the correct language strings
	const raw = (await import(`../../../jsi18n/${LANG}/djangojs.js?raw`)).default
	const context: { django?: Django } = {}
	new Function(raw).call(context)
	django = context.django!
} else {
	django = (globalThis as any).django
}

export const STRINGS = {
	quantity: django.pgettext('widget', 'Quantity'),
	quantity_dec: django.pgettext('widget', 'Decrease quantity'),
	quantity_inc: django.pgettext('widget', 'Increase quantity'),
	filter_events_by: django.pgettext('widget', 'Filter events by'),
	filter: django.pgettext('widget', 'Filter'),
	price: django.pgettext('widget', 'Price'),
	original_price: django.pgettext('widget', 'Original price: %s'),
	new_price: django.pgettext('widget', 'New price: %s'),
	select: django.pgettext('widget', 'Select'),
	select_item: django.pgettext('widget', 'Select %s'),
	select_variant: django.pgettext('widget', 'Select variant %s'),
	sold_out: django.pgettext('widget', 'Sold out'),
	buy: django.pgettext('widget', 'Buy'),
	register: django.pgettext('widget', 'Register'),
	reserved: django.pgettext('widget', 'Reserved'),
	free: django.pgettext('widget', 'FREE'),
	price_from: django.pgettext('widget', 'from %(currency)s %(price)s'),
	image_of: django.pgettext('widget', 'Image of %s'),
	tax_incl: django.pgettext('widget', 'incl. %(rate)s% %(taxname)s'),
	tax_plus: django.pgettext('widget', 'plus %(rate)s% %(taxname)s'),
	tax_incl_mixed: django.pgettext('widget', 'incl. taxes'),
	tax_plus_mixed: django.pgettext('widget', 'plus taxes'),
	quota_left: django.pgettext('widget', 'currently available: %s'),
	unavailable_require_voucher: django.pgettext('widget', 'Only available with a voucher'),
	unavailable_available_from: django.pgettext('widget', 'Not yet available'),
	unavailable_available_until: django.pgettext('widget', 'Not available anymore'),
	unavailable_active: django.pgettext('widget', 'Currently not available'),
	unavailable_hidden_if_item_available: django.pgettext('widget', 'Not yet available'),
	order_min: django.pgettext('widget', 'minimum amount to order: %s'),
	exit: django.pgettext('widget', 'Close ticket shop'),
	loading_error: django.pgettext('widget', 'The ticket shop could not be loaded.'),
	loading_error_429: django.pgettext('widget', 'There are currently a lot of users in this ticket shop. Please open the shop in a new tab to continue.'),
	open_new_tab: django.pgettext('widget', 'Open ticket shop'),
	checkout: django.pgettext('widget', 'Checkout'),
	cart_error: django.pgettext('widget', 'The cart could not be created. Please try again later'),
	cart_error_429: django.pgettext('widget', 'We could not create your cart, since there are currently too many users in this ticket shop. Please click "Continue" to retry in a new tab.'),
	waiting_list: django.pgettext('widget', 'Waiting list'),
	cart_exists: django.pgettext('widget', 'You currently have an active cart for this event. If you select more products, they will be added to your existing cart.'),
	resume_checkout: django.pgettext('widget', 'Resume checkout'),
	redeem_voucher: django.pgettext('widget', 'Redeem a voucher'),
	redeem: django.pgettext('widget', 'Redeem'),
	voucher_code: django.pgettext('widget', 'Voucher code'),
	close: django.pgettext('widget', 'Close'),
	close_checkout: django.pgettext('widget', 'Close checkout'),
	cancel_blocked: django.pgettext('widget', 'You cannot cancel this operation. Please wait for loading to finish.'),
	continue: django.pgettext('widget', 'Continue'),
	variations: django.pgettext('widget', 'Show variants'),
	hide_variations: django.pgettext('widget', 'Hide variants'),
	back_to_list: django.pgettext('widget', 'Choose a different event'),
	back_to_dates: django.pgettext('widget', 'Choose a different date'),
	back: django.pgettext('widget', 'Back'),
	next_month: django.pgettext('widget', 'Next month'),
	previous_month: django.pgettext('widget', 'Previous month'),
	next_week: django.pgettext('widget', 'Next week'),
	previous_week: django.pgettext('widget', 'Previous week'),
	show_seating: django.pgettext('widget', 'Open seat selection'),
	seating_plan_waiting_list: django.pgettext('widget', 'Some or all ticket categories are currently sold out. If you want, you can add yourself to the waiting list. We will then notify if seats are available again.'),
	load_more: django.pgettext('widget', 'Load more'),
	days: {
		MO: django.gettext('Mo'),
		TU: django.gettext('Tu'),
		WE: django.gettext('We'),
		TH: django.gettext('Th'),
		FR: django.gettext('Fr'),
		SA: django.gettext('Sa'),
		SU: django.gettext('Su'),
		MONDAY: django.gettext('Monday'),
		TUESDAY: django.gettext('Tuesday'),
		WEDNESDAY: django.gettext('Wednesday'),
		THURSDAY: django.gettext('Thursday'),
		FRIDAY: django.gettext('Friday'),
		SATURDAY: django.gettext('Saturday'),
		SUNDAY: django.gettext('Sunday'),
	},
	months: {
		'01': django.gettext('January'),
		'02': django.gettext('February'),
		'03': django.gettext('March'),
		'04': django.gettext('April'),
		'05': django.gettext('May'),
		'06': django.gettext('June'),
		'07': django.gettext('July'),
		'08': django.gettext('August'),
		'09': django.gettext('September'),
		10: django.gettext('October'),
		11: django.gettext('November'),
		12: django.gettext('December'),
	} as Record<string, string>,
} as const

export function interpolate (fmt: string, obj: Record<string, unknown> | unknown[], named = false): string {
	return django.interpolate(fmt, obj, named)
}

export function getFormat (formatType: string): string | number {
	return django.get_format(formatType)
}
