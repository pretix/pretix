// The actual gettext implementation is loaded asynchronously with the translation
globalThis.gettext = (msgid) => {
	if (typeof django !== 'undefined' && typeof django.gettext !== 'undefined') {
		return django.gettext(msgid)
	}
	return msgid
}

globalThis.ngettext = (singular, plural, count) => {
	if (typeof django !== 'undefined' && typeof django.ngettext !== 'undefined') {
		return django.ngettext(singular, plural, count)
	}
	return plural
}

globalThis.pgettext = (context, msgid) => {
	if (typeof django !== 'undefined' && typeof django.pgettext !== 'undefined') {
		return django.pgettext(context, msgid)
	}
	return msgid
}

globalThis.interpolate = (fmt, obj, named) => {
	if (named) {
		return fmt.replace(/%\(\w+\)s/g, function (match) { return String(obj[match.slice(2, -2)]) })
	} else {
		return fmt.replace(/%s/g, function (match) { return String(obj.shift()) })
	}
}