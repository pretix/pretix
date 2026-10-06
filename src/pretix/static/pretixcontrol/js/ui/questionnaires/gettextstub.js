// The actual gettext implementation is loaded asynchronously with the translation
export function gettext (msgid) {
	if (typeof django !== 'undefined' && typeof django.gettext !== 'undefined') {
		return django.gettext(msgid)
	}
	return msgid
}

export function ngettext (singular, plural, count) {
	if (typeof django !== 'undefined' && typeof django.ngettext !== 'undefined') {
		return django.ngettext(singular, plural, count)
	}
	return plural
}

export function pgettext (context, msgid) {
	if (typeof django !== 'undefined' && typeof django.pgettext !== 'undefined') {
		return django.pgettext(context, msgid)
	}
	return msgid
}

export function interpolate (fmt, object, named) {
	if (named) {
		return fmt.replace(/%\(\w+\)s/g, function (match) { return String(object[match.slice(2, -2)]) })
	} else {
		return fmt.replace(/%s/g, function (match) { return String(object.shift()) })
	}
}
