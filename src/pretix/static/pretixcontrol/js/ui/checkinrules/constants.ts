/* global gettext, pgettext */

export const TEXTS = {
	and: gettext('All of the conditions below (AND)'),
	or: gettext('At least one of the conditions below (OR)'),
	date_from: gettext('Event start'),
	date_to: gettext('Event end'),
	date_admission: gettext('Event admission'),
	date_custom: gettext('custom date and time'),
	date_customtime: gettext('custom time'),
	date_tolerance: gettext('Tolerance (minutes)'),
	condition_add: gettext('Add condition'),
	minutes: gettext('minutes'),
	duplicate: gettext('Duplicate'),
	status_present: pgettext('entry_status', 'present'),
	status_absent: pgettext('entry_status', 'absent'),
}

export const TYPEOPS = {
	// Every change to our supported JSON logic must be done
	// * in pretix.base.services.checkin
	// * in pretix.base.models.checkin
	// * in pretix.helpers.jsonlogic_boolalg
	// * in checkinrules.js
	// * in libpretixsync
	// * in pretixscan-ios
	product: {
		inList: {
			label: gettext('is one of'),
			cardinality: 2,
		}
	},
	variation: {
		inList: {
			label: gettext('is one of'),
			cardinality: 2,
		}
	},
	gate: {
		inList: {
			label: gettext('is one of'),
			cardinality: 2,
		}
	},
	datetime: {
		isBefore: {
			label: gettext('is before'),
			cardinality: 2,
		},
		isAfter: {
			label: gettext('is after'),
			cardinality: 2,
		},
	},
	enum_entry_status: {
		'==': {
			label: gettext('='),
			cardinality: 2,
		},
	},
	int_by_datetime: {
		'<': {
			label: '<',
			cardinality: 2,
		},
		'<=': {
			label: '≤',
			cardinality: 2,
		},
		'>': {
			label: '>',
			cardinality: 2,
		},
		'>=': {
			label: '≥',
			cardinality: 2,
		},
		'==': {
			label: '=',
			cardinality: 2,
		},
		'!=': {
			label: '≠',
			cardinality: 2,
		},
	},
	int: {
		'<': {
			label: '<',
			cardinality: 2,
		},
		'<=': {
			label: '≤',
			cardinality: 2,
		},
		'>': {
			label: '>',
			cardinality: 2,
		},
		'>=': {
			label: '≥',
			cardinality: 2,
		},
		'==': {
			label: '=',
			cardinality: 2,
		},
		'!=': {
			label: '≠',
			cardinality: 2,
		},
	},
}

export const VARS = {
	product: {
		label: gettext('Product'),
		type: 'product',
	},
	variation: {
		label: gettext('Product variation'),
		type: 'variation',
	},
	gate: {
		label: gettext('Gate'),
		type: 'gate',
	},
	now: {
		label: gettext('Current date and time'),
		type: 'datetime',
	},
	now_isoweekday: {
		label: gettext('Current day of the week (1 = Monday, 7 = Sunday)'),
		type: 'int',
	},
	entry_status: {
		label: gettext('Current entry status'),
		type: 'enum_entry_status',
	},
	entries_number: {
		label: gettext('Number of previous entries'),
		type: 'int',
	},
	entries_today: {
		label: gettext('Number of previous entries since midnight'),
		type: 'int',
	},
	entries_since: {
		label: gettext('Number of previous entries since'),
		type: 'int_by_datetime',
	},
	entries_before: {
		label: gettext('Number of previous entries before'),
		type: 'int_by_datetime',
	},
	entries_days: {
		label: gettext('Number of days with a previous entry'),
		type: 'int',
	},
	entries_days_since: {
		label: gettext('Number of days with a previous entry since'),
		type: 'int_by_datetime',
	},
	entries_days_before: {
		label: gettext('Number of days with a previous entry before'),
		type: 'int_by_datetime',
	},
	minutes_since_last_entry: {
		label: gettext('Minutes since last entry (-1 on first entry)'),
		type: 'int',
	},
	minutes_since_first_entry: {
		label: gettext('Minutes since first entry (-1 on first entry)'),
		type: 'int',
	},
}

export const DATETIME_OPTIONS = {
	format: document.body.dataset.datetimeformat,
	locale: document.body.dataset.datetimelocale,
	useCurrent: false,
	icons: {
		time: 'fa fa-clock-o',
		date: 'fa fa-calendar',
		up: 'fa fa-chevron-up',
		down: 'fa fa-chevron-down',
		previous: 'fa fa-chevron-left',
		next: 'fa fa-chevron-right',
		today: 'fa fa-screenshot',
		clear: 'fa fa-trash',
		close: 'fa fa-remove'
	}
}
